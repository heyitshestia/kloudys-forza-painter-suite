async (page, options = {}) => {
  const count = options.count || 300;
  const samples = options.samples || 3;
  const cdp = await page.context().newCDPSession(page);
  const save = (name, data) => fs.writeFileSync(path.join(output, name), JSON.stringify(data, null, 2));
  await page.evaluate(() => {
    window.renderAudit = { stage: 'load', rows: {} };
    window.auditReset = stage => { renderAudit = { stage, rows: {} }; };
    const wrap = (owner, name, label = name) => {
      if (typeof owner[name] !== 'function') return;
      const original = owner[name];
      owner[name] = function (...args) {
        const started = performance.now();
        try { return original.apply(this, args); }
        finally {
          const row = renderAudit.rows[label] ||= { calls: 0, ms: 0, max: 0 };
          const ms = performance.now() - started;
          row.calls++; row.ms += ms; row.max = Math.max(row.max, ms);
          if (label === 'object.render' && ms > 5) {
            const key = `${this.kloudy?.resource_family}:${this.kloudy?.resource_index}:${this.kloudyMaskCutout ? 'cutout' : this.kloudyMaskOutline ? 'outline' : this.type}`;
            const slow = (renderAudit.slow ||= {})[key] ||= { calls: 0, ms: 0, max: 0,
              composite: this.globalCompositeOperation, shadow: this.shadow, opacity: this.opacity,
              size: [this.width, this.height], cache: [this._cacheCanvas?.width, this._cacheCanvas?.height] };
            slow.calls++; slow.ms += ms; slow.max = Math.max(slow.max, ms);
          }
        }
      };
    };
    for (const name of ['renderAll', 'renderCanvas', '_renderObjects', 'findTarget', 'isTargetTransparent']) wrap(canvas, name);
    for (const name of ['render', 'renderCache', 'drawCacheOnCanvas', 'drawObject', '_updateCacheCanvas']) wrap(fabric.Object.prototype, name, `object.${name}`);
    for (const name of ['renderNativeTriangleFill', 'syncSelectedShapeOutlines', 'syncMaskPreviewForTarget',
      'syncMaskPreviewOutlines', 'syncCanvasObjectCoords', 'updateSelectionPanel', 'pushHistory',
      'snapTargetToGuides', 'captureSharedHistoryState', 'refreshLayers']) wrap(window, name);
    window.auditSnapshot = () => JSON.stringify(snapshotShapes());
  });
  const setup = await page.evaluate(async ({ count, baselineDraw, complex }) => {
    const slots = [1, 2, 30, 36, 39, 31, 12, 5];
    const cols = Math.ceil(Math.sqrt(count * 1.5));
    const rows = Math.ceil(count / cols);
    const shapes = Array.from({ length: count }, (_, i) => {
      const gradient = i % 17 === 8;
      const family = gradient ? 'Gradient_Shapes' : complex ?
        ['Tribal', 'Nature', 'Tears', 'Flames', 'Paint_Splats', 'Racing_Icons', 'Upper_Letters_1', 'Primitives'][Math.floor(i / slots.length) % 8] : 'Primitives';
      const slot = gradient ? 1 : slots[i % slots.length];
      const mask = i > 0 && i % 53 === 0;
      return { type: editorCatalog.resourceToTypeCode(family, slot),
        resource_family: family, resource_index: slot,
        editor_id: `perf-${i}`, shape_name: `Performance ${i}`,
        color: [45 + i * 37 % 190, 40 + i * 73 % 190, 50 + i * 23 % 180, i % 3 ? 255 : 151], mask,
        data: [(i % cols - (cols - 1) / 2) * 38, (Math.floor(i / cols) - (rows - 1) / 2) * 38,
          (i % 7 ? 1 : -1) * .4, .32 + i % 4 * .04, i % 6 * 17, 0, mask ? 1 : 0] };
    });
    const started = performance.now();
    await loadPayload({ shapes });
    const loaded = performance.now() - started;
    const zoom = Math.min((canvas.width - 80) / (cols * 38 + 100), (canvas.height - 80) / (rows * 38 + 100));
    canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2, canvas.height / 2]);
    const objects = vinylObjects();
    if (baselineDraw) for (const object of objects) {
      if (object.drawCacheOnCanvas === renderNativePathCache) object.drawCacheOnCanvas = fabric.Object.prototype.drawCacheOnCanvas;
    }
    return { count, loadMs: loaded, zoom, canvas: [canvas.width, canvas.height], dpr: devicePixelRatio,
      pathCommands: objects.reduce((n, o) => n + (o.path?.length || 0), 0),
      maxPathCommands: Math.max(...objects.map(o => o.path?.length || 0)),
      masks: objects.filter(o => o.kloudy.mask).length,
      images: objects.filter(o => o.type === 'image').length,
      visible: objects.filter(o => o.isOnScreen()).length,
      renderer: editorRenderer.disabledReason, loadBreakdown: renderAudit };
  }, { count, baselineDraw: !!options.baselineDraw, complex: !!options.complex });
  save('setup.json', setup); console.log(JSON.stringify({ stage: 'setup', ...setup }));
  if (options.compareBaseline || options.compareNonTriangle) {
    const comparison = await page.evaluate(nonTriangleOnly => {
      const objects = vinylObjects().filter(o => o.drawCacheOnCanvas === renderNativePathCache
        && (!nonTriangleOnly || o._renderPathCommands !== renderNativeTriangleFill));
      const times = [];
      const read = () => canvas.contextContainer.getImageData(0, 0, canvas.lowerCanvasEl.width, canvas.lowerCanvasEl.height).data;
      let expected;
      try {
        objects.forEach(o => { o.drawCacheOnCanvas = fabric.Object.prototype.drawCacheOnCanvas; });
        for (let i = 0; i < 3; i++) {
          const started = performance.now(); canvas.renderAll(); times.push(performance.now() - started);
        }
        expected = read();
      } finally { objects.forEach(o => { o.drawCacheOnCanvas = renderNativePathCache; }); }
      canvas.renderAll(); const actual = read();
      let changed = 0;
      for (let i = 0; i < actual.length; i++) if (actual[i] !== expected[i]) changed++;
      if (changed) throw Error(`Same-process baseline comparison changed ${changed} channels`);
      return { baselineMs: times, exactPixels: true, comparedObjects: objects.length };
    }, !!options.compareNonTriangle);
    save('baseline-repeat.json', comparison);
  }
  await cdp.send('Profiler.enable');
  await cdp.send('Profiler.setSamplingInterval', { interval: 1000 });
  await cdp.send('Profiler.start');
  await page.evaluate(() => auditReset('render'));
  const times = [];
  for (let i = 0; i < samples; i++) {
    times.push(await page.evaluate(() => {
      const started = performance.now(); canvas.renderAll(); return performance.now() - started;
    }));
    save('render-progress.json', { times });
  }
  const render = await page.evaluate(() => {
    return { breakdown: renderAudit,
      cachePixels: vinylObjects().reduce((n, o) => n + (o._cacheCanvas?.width || 0) * (o._cacheCanvas?.height || 0), 0) };
  });
  const sortedTimes = times.slice().sort((a, b) => a - b);
  Object.assign(render, { times, p95: sortedTimes[Math.ceil(sortedTimes.length * .95) - 1] });
  save('render.json', render); console.log(JSON.stringify({ stage: 'render', ...render }));
  const profile = (await cdp.send('Profiler.stop')).profile;
  save('render.cpuprofile', profile);
  if (!options.renderOnly) {
    await page.evaluate(() => {
      selectObjects(vinylObjects().filter(o => !o.kloudy.mask), 'performance bulk selection');
      canvas.renderAll();
      window.auditBefore = auditSnapshot();
      auditReset('gesture');
      window.auditMoves = [];
      canvas.on('object:moving', () => auditMoves.push(performance.now()));
    });
    const center = await page.evaluate(() => {
      const p = fabric.util.transformPoint(canvas.getActiveObject().getCenterPoint(), canvas.viewportTransform);
      const box = canvas.upperCanvasEl.getBoundingClientRect();
      return { x: box.left + p.x, y: box.top + p.y };
    });
    const moves = [];
    await page.mouse.move(center.x, center.y);
    await page.mouse.down();
    for (let i = 1; i <= samples; i++) {
      const started = Date.now();
      await page.mouse.move(center.x + i * 4, center.y + i * 3);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
      moves.push(Date.now() - started);
      save('gesture-progress.json', { movesMs: moves });
    }
    await page.mouse.up();
    const gesture = await page.evaluate(() => {
      window.auditAfter = auditSnapshot();
      if (auditAfter === auditBefore || auditMoves.length === 0) throw Error('Real pointer drag did not move selection');
      return { events: auditMoves.length, selected: selectedVinylObjects().length, breakdown: renderAudit };
    });
    const sorted = moves.slice().sort((a, b) => a - b);
    Object.assign(gesture, { movesMs: moves, p95: sorted[Math.ceil(sorted.length * .95) - 1] });
    save('gesture.json', gesture); console.log(JSON.stringify({ stage: 'gesture', ...gesture }));
    const correctness = await page.evaluate(async () => {
      await undo();
      if (auditSnapshot() !== auditBefore) throw Error('Undo serialization mismatch');
      await redo();
      if (auditSnapshot() !== auditAfter) throw Error('Redo serialization mismatch');
      const expected = auditSnapshot();
      await loadPayload({ shapes: JSON.parse(expected) });
      if (auditSnapshot() !== expected) throw Error('Serialized shapes reload mismatch');
      return { exactUndo: true, exactRedo: true, exactSerializedReload: true };
    });
    save('correctness.json', correctness);
  }
  await cdp.detach();
  if (options.saveProject) {
    const expected = await page.evaluate(() => JSON.stringify(snapshotShapes()));
    const portable = await page.evaluate(() => JSON.stringify(vinylObjects().map(o => objectToShape(o, { includeEditorMeta: false }))));
    await page.locator('#workspaceFileMenu').click();
    await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill('Performance complex qualification');
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    const processInfo = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
    const projectDir = path.join(processInfo.profile, 'projects');
    const projectName = fs.readdirSync(projectDir).find(name => name.endsWith('.json'));
    const saved = JSON.parse(fs.readFileSync(path.join(projectDir, projectName), 'utf8'));
    if (JSON.stringify(saved.shapes) !== expected || saved.layer_count !== count) throw Error('Saved project included helpers or changed shapes');
    save('project-readback.json', { exactShapes: true, layerCount: saved.layer_count, helpersExcluded: true });
    await page.evaluate(() => exportJson());
    const exportName = fs.readdirSync(processInfo.exportRoot, { recursive: true }).find(name => name.endsWith('.json'));
    if (!exportName) throw Error('Portable export file was not found in the isolated export directory');
    const exported = JSON.parse(fs.readFileSync(path.join(processInfo.exportRoot, exportName), 'utf8'));
    if (JSON.stringify(exported.shapes) !== portable) throw Error('Export included helpers or changed artwork');
    save('export-readback.json', exported);
    await page.reload();
    await page.waitForFunction(() => window.KfpsDesktop?.ready);
    await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(d => d.close()));
    await page.evaluate(() => openProjectBrowser());
    await page.waitForFunction(() => document.querySelectorAll('#projectBrowserEntries button').length > 0);
    await page.locator('#projectBrowserEntries button').filter({ hasText: 'Performance complex qualification' }).dblclick();
    await page.waitForFunction(count => !editorCommands.busy && vinylObjects().length === count, count);
    if (await page.evaluate(() => JSON.stringify(snapshotShapes())) !== expected) throw Error('Saved project reopen mismatch');
    save('save-correctness.json', { exactProjectReadback: true, exactPortableExport: true,
      exactProjectReopen: true, layerCount: count, helpersExcluded: true });
  }
  return { count, setup, render, softwareOffscreenOnly: true };
}
