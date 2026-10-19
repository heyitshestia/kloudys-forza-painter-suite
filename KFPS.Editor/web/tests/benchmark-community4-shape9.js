async (page, options = {}) => {
  const save = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2));
  const setup = await page.evaluate(async () => {
    window.shape9Audit = {};
    const wrap = (owner, name, label = name) => {
      const original = owner[name];
      if (typeof original !== 'function') return;
      owner[name] = function (...args) {
        const start = performance.now();
        try { return original.apply(this, args); }
        finally {
          const key = label === 'object.render' ? `${label}:${this.kloudySelectionOutlineHelper ? 'selection' : this.kloudy ? 'vinyl' : 'other'}` : label;
          const row = shape9Audit[key] ||= { calls: 0, ms: 0, max: 0 };
          const elapsed = performance.now() - start;
          row.calls++; row.ms += elapsed; row.max = Math.max(row.max, elapsed);
        }
      };
    };
    for (const key of ['renderAll', 'findTarget', 'isTargetTransparent']) wrap(canvas, key);
    for (const key of ['render', 'renderCache', 'drawObject']) wrap(fabric.Object.prototype, key, `object.${key}`);
    for (const key of ['syncSelectedShapeOutlines', 'syncMaskPreviewForTarget', 'refreshLayers']) wrap(window, key);
    await loadPayload({ shapes: [{ type: editorCatalog.resourceToTypeCode('Community_Vinyls_4', 9),
      resource_family: 'Community_Vinyls_4', resource_index: 9, editor_id: 'community-4-shape-9',
      color: [230, 60, 120, 255], data: [0, 0, 2, 2, 0, 0, 0] }] });
    const object = vinylObjects()[0];
    canvas.setViewportTransform([2, 0, 0, 2, canvas.width / 2, canvas.height / 2]);
    canvas.discardActiveObject();
    syncSelectedShapeOutlines();
    canvas.renderAll();
    return { type: object.kloudy.type, commands: object.path.length, size: [object.width, object.height],
      complexity: object.kloudy.render_complexity, renderer: editorRenderer.disabledReason,
      dpr: devicePixelRatio, viewport: [innerWidth, innerHeight], userAgent: navigator.userAgent };
  });
  save('shape9-setup.json', setup);
  const stages = [];
  const measure = async (stage, mode = 'idle') => {
    const result = await page.evaluate(({ stage, mode }) => {
      window.shape9Audit = {};
      const object = vinylObjects()[0], times = [];
      for (let i = 0; i < 12; i++) {
        const start = performance.now();
        if (mode === 'move') {
          object.set({ left: object.left + 2, top: object.top + 1 });
          object.setCoords();
          syncSelectedShapeOutlines();
        } else if (mode === 'scale') {
          object.set({ scaleX: 2 + i * .01, scaleY: 2 - i * .01 });
          object.setCoords();
          syncSelectedShapeOutlines();
        } else if (mode === 'recolor') {
          object.set({ fill: i % 2 ? '#ff3060' : '#30aaff', dirty: true });
          syncSelectedShapeOutlines();
        }
        canvas.renderAll();
        times.push(performance.now() - start);
      }
      const sorted = times.slice().sort((a, b) => a - b);
      const helper = selectedShapeOutlineHelpers.get(object);
      return { stage, mode, times, median: sorted[6], p95: sorted[11], audit: shape9Audit,
        helper: helper && { commands: helper.path?.length, cache: [helper._cacheCanvas?.width, helper._cacheCanvas?.height],
          dirty: helper.dirty, ownCaching: helper.ownCaching, objectCaching: helper.objectCaching,
          clipCommands: helper.clipPath?.path.length } };
    }, { stage, mode });
    stages.push(result);
    save('shape9-stages.json', stages);
  };
  await measure('unselected');
  await page.evaluate(() => selectObjects(vinylObjects(), 'Shape 9 performance reproduction'));
  await page.waitForFunction(() => selectedShapeOutlineHelpers.get(vinylObjects()[0])?.kloudySelectionOutlineUsesResourcePath);
  await measure('selected');
  await measure('selected-move', 'move');
  await measure('selected-scale', 'scale');
  await measure('selected-recolor', 'recolor');
  await page.screenshot({ path: path.join(output, 'shape9-selected.png') });
  if (options.diagnose) {
    await page.evaluate(() => { selectedShapeOutlineHelpers.get(vinylObjects()[0]).visible = false; });
    await measure('hidden-outline');
    await page.evaluate(() => {
      const helper = selectedShapeOutlineHelpers.get(vinylObjects()[0]);
      helper.visible = true;
      window.shape9Clip = helper.clipPath;
      helper.clipPath = null;
      helper.dirty = true;
    });
    await measure('unclipped-outline');
    await measure('unclipped-move', 'move');
    await page.evaluate(() => {
      const helper = selectedShapeOutlineHelpers.get(vinylObjects()[0]);
      helper.clipPath = shape9Clip;
      helper.objectCaching = true;
      helper.dirty = true;
    });
    await measure('cached-outline');
    await measure('cached-move', 'move');
    await measure('cached-scale', 'scale');
    const candidate = await page.evaluate(() => {
      const object = vinylObjects()[0];
      const read = () => canvas.contextContainer.getImageData(0, 0, canvas.lowerCanvasEl.width, canvas.lowerCanvasEl.height).data;
      object.dirty = true;
      canvas.renderAll();
      const expected = read();
      object._renderPathCommands = renderNativeTriangleFill;
      object.dirty = true;
      canvas.renderAll();
      const actual = read();
      let channels = 0, maximum = 0;
      for (let i = 0; i < actual.length; i++) {
        if (actual[i] !== expected[i]) channels++;
        maximum = Math.max(maximum, Math.abs(actual[i] - expected[i]));
      }
      return { channels, maximum, firstCommands: object.path.slice(0, 7) };
    });
    save('shape9-candidate.json', candidate);
    await measure('native-triangle-scale', 'scale');
    await measure('native-triangle-recolor', 'recolor');
  }
  await page.evaluate(() => markCurrentHistorySaved('Isolated shape 9 benchmark'));
  return { setup, stages };
}
