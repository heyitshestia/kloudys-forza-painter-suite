async (page, options) => {
  if (!options.reference) throw Error('A local reference fixture is required');
  page.setDefaultTimeout(30000);
  const check = (value, message) => { if (!value) throw Error(message); };
  const rows = [], faults = [], cycles = Number(options.cycles || 12);
  const profiler = options.profile ? await page.context().newCDPSession(page) : null;
  if (profiler) await profiler.send('Profiler.enable');
  const write = () => fs.writeFileSync(path.join(output, 'reference-quarter-progress.json'), JSON.stringify({ rows, faults }, null, 2));
  page.on('crash', () => { faults.push('page-crash'); write(); });
  page.on('pageerror', error => { faults.push(String(error)); write(); });
  page.on('console', message => {
    if (message.type() === 'error') { faults.push(message.text().slice(0, 1200)); write(); }
  });
  await page.evaluate(() => {
    window.reportMeasure = null;
    window.reportFrameStop = false;
    window.reportObserver = new PerformanceObserver(list => {
      if (reportMeasure) reportMeasure.tasks.push(...list.getEntries().map(e => ({ ms: e.duration, at: e.startTime })));
    });
    reportObserver.observe({ entryTypes: ['longtask'] });
    let last = 0;
    const frame = now => {
      if (reportMeasure && last && reportMeasure.frames.length < 20000) reportMeasure.frames.push(now - last);
      last = now;
      if (!reportFrameStop) requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
  const start = async () => {
    if (profiler) await profiler.send('Profiler.start');
    await page.evaluate(() => { reportMeasure = { frames: [], tasks: [], started: performance.now() }; });
  };
  const stop = async name => {
    await page.waitForTimeout(options.settleMs || 80);
    const metrics = await page.evaluate(() => {
      const m = reportMeasure; reportMeasure = null;
      const f = m.frames.slice(1).sort((a, b) => a - b);
      return { elapsedMs: performance.now() - m.started, frames: f.length,
        p95: f[Math.floor(f.length * .95)] || 0, max: Math.max(0, ...f),
        gaps50: f.filter(v => v >= 50).length, gaps100: f.filter(v => v >= 100).length,
        tasks: m.tasks, layers: vinylObjects().length, zoom: canvas.getZoom(),
        samplerTiles: editorReference.sampler?.tiles?.size || 0,
        reference: editorReference.image ? [editorReference.image.width, editorReference.image.height] : null };
    });
    if (profiler) {
      const { profile } = await profiler.send('Profiler.stop');
      fs.writeFileSync(path.join(output, `${name}.cpuprofile`), JSON.stringify(profile));
      const nodes = new Map(profile.nodes.map(n => [n.id, n.callFrame]));
      const times = new Map();
      for (let i = 0; i < (profile.samples || []).length; i++) {
        const f = nodes.get(profile.samples[i]);
        const key = `${f.functionName || 'anonymous'} ${f.url.split('/').pop()}:${f.lineNumber + 1}`;
        times.set(key, (times.get(key) || 0) + (profile.timeDeltas[i] || 0) / 1000);
      }
      metrics.cpuTop = [...times].sort((a, b) => b[1] - a[1]).slice(0, 15);
    }
    rows.push({ name, ...metrics }); write();
  };
  const geometry = () => page.evaluate(() => {
    const o = canvas.getActiveObject();
    if (!o?.kloudy) throw Error('The target shape is not selected');
    o.setCoords();
    const box = canvas.upperCanvasEl.getBoundingClientRect();
    const screen = p => { const q = fabric.util.transformPoint(p, canvas.viewportTransform); return { x: box.left + q.x, y: box.top + q.y }; };
    const matrix = o.calcTransformMatrix();
    let grab;
    for (const x of [-.3, -.15, 0, .15, .3]) {
      for (const y of [-.3, -.15, 0, .15, .3]) {
        const point = fabric.util.transformPoint(new fabric.Point(o.width * x, o.height * y), matrix);
        if (KfpsFabricAdapter.visiblePixelAt(canvas, o, point)) { grab = screen(point); break; }
      }
      if (grab) break;
    }
    if (!grab) throw Error('No painted target point');
    const local = p => ({ x: box.left + p.x, y: box.top + p.y });
    return { grab, center: screen(o.getCenterPoint()), rotate: local(o.oCoords.mtr),
      right: local(o.oCoords.mr), corner: local(o.oCoords.br), left: o.left, top: o.top,
      angle: o.angle, scaleX: o.scaleX, scaleY: o.scaleY, skewX: o.skewX, skewY: o.skewY };
  });
  const drag = async (a, b, shift = false) => {
    if (shift) await page.keyboard.down('Shift');
    try { await page.mouse.move(a.x, a.y); await page.mouse.down(); await page.mouse.move(b.x, b.y, { steps: 6 }); await page.mouse.up(); }
    finally { if (shift) await page.keyboard.up('Shift'); }
  };
  const runtime = await page.evaluate(() => ({ userAgent: navigator.userAgent, dpr: devicePixelRatio,
    screen: [screen.width, screen.height], inner: [innerWidth, innerHeight], hidden: document.hidden,
    language: navigator.language, fabric: fabric.version }));
  rows.push({ name: 'runtime', ...runtime }); write();
  check(await page.evaluate(() => vinylObjects().length === 0), 'Report requires a fresh empty profile');
  await page.locator('#newCanvas').click();
  await page.locator('[data-tool-mode="overlay"]').click();
  await start();
  // The Qt process and fixture share this filesystem. Avoid Playwright's remote
  // base64 File construction, which adds an artificial main-thread import stall.
  const fileSession = await page.context().newCDPSession(page);
  try {
    const { root } = await fileSession.send('DOM.getDocument', { depth: 0 });
    const { nodeId } = await fileSession.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#overlayInput' });
    await fileSession.send('DOM.setFileInputFiles', { nodeId, files: [options.reference] });
  } finally { await fileSession.detach(); }
  await page.waitForFunction(() => editorReference.image && !recoveryRestoreDepth);
  await stop('reference-import');
  check(await page.evaluate(() => editorReference.image.width === 5888 && editorReference.image.height === 2816), 'Reference dimensions changed');
  await start();
  await page.locator('#overlayOpacity').focus();
  await page.keyboard.press('Home');
  for (let i = 0; i < 7; i++) await page.keyboard.press('ArrowRight');
  await page.keyboard.press('End');
  for (let i = 0; i < 4; i++) await page.keyboard.press('ArrowLeft');
  await stop('opacity-slider');
  const referenceBefore = await page.evaluate(() => ({ opacity: editorReference.image.opacity,
    left: editorReference.image.left, top: editorReference.image.top, sx: editorReference.image.scaleX, sy: editorReference.image.scaleY }));
  await start();
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Reference quarter report');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await stop('save-as-with-reference');
  await page.locator('#fitView').click();
  await start();
  for (let slot = 0; slot < 8; slot++) {
    await page.locator('[data-tool-mode="dropper"]').click();
    const b = await page.locator('.upper-canvas').boundingBox();
    await page.mouse.click(b.x + b.width * (.3 + slot * .05), b.y + b.height * .6);
    const color = await page.evaluate(() => currentPanelColor());
    await page.locator('#quickColorSwatch').click();
    await page.locator('#favoriteColorGrid button').nth(slot).click();
    await page.locator('#saveFavoriteColor').click();
    check(await page.evaluate(({ slot, color }) => JSON.stringify(favoriteColors[slot]) === JSON.stringify(color), { slot, color }), 'Saved eyedropper color differs');
    await page.locator('#closeColorDialog').click();
  }
  check(await page.evaluate(() => editorReference.sampler.tiles.size > 0), 'Eyedropper did not sample reference pixels');
  await page.locator('[data-tool-mode="select"]').click();
  await stop('reference-eyedropper-palette');
  const bounds = await page.locator('.upper-canvas').boundingBox();
  await start();
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  for (let i = 0; i < Number(options.zoomSteps || 8); i++) await page.mouse.wheel(0, -160);
  await stop('zoom-before-insertion');
  await start();
  await page.locator('[data-tool-mode="shapeLibrary"]').click();
  await page.locator('#shapeFamily').selectOption('Primitives');
  await page.locator('#shapeSearch').fill('');
  await page.locator('#shapeGrid .shapeTile').nth(Number(options.slot || 30) - 1).locator('img').click();
  await page.waitForFunction(() => vinylObjects().length === 1 && selectedVinylObjects().length === 1);
  const layers = Number(options.layers || 1);
  for (let count = 1; count < layers; count++) {
    await page.locator('#shapeGrid .shapeTile').nth(Number(options.slot || 30) - 1).locator('img').click();
    await page.waitForFunction(expected => vinylObjects().length === expected && selectedVinylObjects().length === 1, count + 1);
  }
  await stop('quarter-insertion');
  rows.push({ name: 'target', layers, shape: await page.evaluate(() => snapshotShapes().at(-1)) }); write();
  const rounds = Number(options.rounds || 1);
  for (let round = 0; round < rounds; round++) for (const order of ['below', 'above']) {
    await page.locator('[data-tool-mode="overlay"]').click();
    await page.locator('#overlayLayerMode').selectOption(order);
    await page.locator('[data-tool-mode="select"]').click();
    await start();
    for (let i = 0; i < cycles; i++) {
      const original = options.restoreEachCycle ? await page.evaluate(() => JSON.stringify(snapshotShapes())) : null;
      const before = await geometry(), c = before.center, r = before.rotate;
      const dx = r.x - c.x, dy = r.y - c.y, turn = i % 2 ? -.35 : .35;
      await page.mouse.move(r.x, r.y); await page.mouse.down();
      for (let step = 1; step <= 8; step++) {
        const a = turn * step / 8;
        await page.mouse.move(c.x + dx * Math.cos(a) - dy * Math.sin(a), c.y + dx * Math.sin(a) + dy * Math.cos(a));
      }
      await page.mouse.up();
      const rotated = await geometry();
      await drag(rotated.grab, { x: rotated.grab.x + 12, y: rotated.grab.y + 6 });
      const moved = await geometry();
      check(Math.abs(rotated.angle - before.angle) > 5, 'Pointer rotation did not turn the target');
      check(Math.hypot(moved.left - rotated.left, moved.top - rotated.top) > .1, 'Immediate move did not move target');
      await page.mouse.move(moved.center.x, moved.center.y);
      for (const delta of [-160, 160, -160, 160]) await page.mouse.wheel(0, delta);
      const zoomed = await geometry();
      await drag(zoomed.grab, { x: zoomed.grab.x - 12, y: zoomed.grab.y - 6 });
      const resize = await geometry();
      await drag(resize.right, { x: resize.right.x + (i % 2 ? -5 : 5), y: resize.right.y + 2 });
      const resized = await geometry();
      check(Math.abs(resized.scaleX - resize.scaleX) > 1e-5 || Math.abs(resized.scaleY - resize.scaleY) > 1e-5, 'Resize did not change geometry');
      if (i % 4 === 0) {
        const skew = await geometry();
        await drag(skew.corner, { x: skew.corner.x + 5, y: skew.corner.y - 3 }, true);
      }
      if (original) {
        let restored = false;
        for (let attempt = 0; attempt <= 8; attempt++) {
          if (await page.evaluate(expected => JSON.stringify(snapshotShapes()) === expected, original)) { restored = true; break; }
          await page.locator('#undoBtn').click();
          await page.waitForFunction(() => !editorCommands.busy);
        }
        check(restored, 'Pointer cycle did not undo to the exact original shape');
        if (!await page.evaluate(() => selectedVinylObjects().length === 1)) await page.locator('.layerRow').first().click();
      }
    }
    const suffix = rounds > 1 ? `${order}-${round + 1}` : order;
    await stop(`rotate-immediate-move-zoom-resize-${suffix}`);
    await page.screenshot({ path: path.join(output, `reference-quarter-${suffix}.png`) });
    const recovery = await page.evaluate(async () => {
      const started = performance.now(); await flushPendingAutosave();
      const payload = await readAutosavePayload();
      if (JSON.stringify(payload.shapes) !== JSON.stringify(snapshotShapes())) throw Error('Recovery shape mismatch');
      return { waitedMs: performance.now() - started, exactShapes: true, referencePresent: !!payload.editor_source_overlay };
    });
    rows.push({ name: `recovery-${suffix}`, ...recovery }); write();
  }
  await page.locator('#saveProject').click();
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  const snapshot = await page.evaluate(() => JSON.stringify(snapshotShapes()));
  await page.locator('#newCanvas').click();
  await page.waitForFunction(() => vinylObjects().length === 0);
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({ has: page.getByText('Reference quarter report', { exact: true }) }).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(expected => vinylObjects().length === expected && editorReference.image && !recoveryRestoreDepth && !documentDirty, layers);
  check(await page.evaluate(expected => JSON.stringify(snapshotShapes()) === expected, snapshot), 'Saved shape reopen differs');
  const referenceAfter = await page.evaluate(() => ({ opacity: editorReference.image.opacity,
    left: editorReference.image.left, top: editorReference.image.top, sx: editorReference.image.scaleX, sy: editorReference.image.scaleY }));
  check(JSON.stringify(referenceBefore) === JSON.stringify(referenceAfter), 'Saved reference opacity/transform differs');
  await page.evaluate(() => { reportFrameStop = true; reportObserver.disconnect(); });
  if (profiler) await profiler.detach();
  check(!faults.length, `Unexpected editor errors: ${faults.join('; ')}`);
  return { cycles: cycles * 2 * rounds, rows, faults, exactSavedReopen: true, referenceTransformRetained: true,
    input: 'Actual file input, slider keyboard, Save As/Enter, eyedropper, palette, tile, wheel and pointer controls; assertions read scene' };
}
