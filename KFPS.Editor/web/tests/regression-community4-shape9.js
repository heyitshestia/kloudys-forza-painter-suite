async (page, options = {}) => {
  const save = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2));
  const load = async (count = 1) => page.evaluate(async count => {
    await loadPayload({ shapes: Array.from({ length: count }, (_, i) => ({
      type: i === count - 1 ? editorCatalog.resourceToTypeCode('Community_Vinyls_4', 9) : 1048677,
      color: [50, 135, 200, 255], editor_id: `shape9-check-${i}`,
      data: i === count - 1 ? [0, 0, 1.8, 1.8, 0, 0, 0]
        : [-250 + i % 20 * 25, -160 + Math.floor(i / 20) * 24, .05, .05, 0, 0, 0],
    })) });
    canvas.setViewportTransform([1.7, 0, 0, 1.7, canvas.width / 2, canvas.height / 2]);
    selectObjects([vinylObjects().at(-1)], 'Shape 9 regression');
    if (selectionOutlinePathPromises.size) await Promise.all(selectionOutlinePathPromises.values());
  }, count);
  await load();
  const pixels = await page.evaluate(() => {
    const object = vinylObjects()[0];
    if (object._renderPathCommands !== renderNativeTriangleFill) throw Error('Bounds anchors disabled the native fast fill');
    const factories = [];
    const options = { originX: 'center', originY: 'center', left: 23, top: -17,
      scaleX: 1.7, scaleY: .6, angle: 31, skewX: 13, strokeWidth: 0 };
    const bounds = value => JSON.stringify({ width: value.width, height: value.height,
      pathOffset: value.pathOffset, left: value.left, top: value.top, matrix: value.calcOwnMatrix(),
      coordinates: value.getCoords().map(p => [p.x, p.y]) });
    for (const [label, data] of [['resource', object.kloudy.mesh_path],
      ['external-anchors', 'M -90 -80 M 90 80 M 1 2 L 3 4 L 8 -9 Z']]) {
      const original = new fabric.Path(data, options);
      const first = makeCachedFabricPath(data, options, `shape9-regression-${label}`);
      const second = makeCachedFabricPath(data, options, `shape9-regression-${label}`);
      for (const candidate of [first, second]) {
        if (bounds(candidate) !== bounds(original) || JSON.stringify(candidate.path) !== JSON.stringify(original.path)) {
          throw Error(`${label}: optimized factory changed bounds, coordinates or path`);
        }
      }
      if (first.path !== second.path || !Object.isFrozen(first.path)) throw Error('Native cached path is not safely shared');
      second.set({ left: 91, angle: -51, scaleX: .37 });
      if (bounds(first) !== bounds(original)) throw Error('Shared commands leaked instance transforms');
      for (const item of [original, first, second]) discardFabricObject(item);
      factories.push({ label, exactFreshAndCachedBounds: true, independentTransforms: true });
    }
    const geometry = JSON.stringify(object.path), rows = [];
    const read = () => canvas.contextContainer.getImageData(0, 0, canvas.lowerCanvasEl.width, canvas.lowerCanvasEl.height).data;
    for (const [zoom, angle, skew, flipX, opacity] of [
      [.04, 0, 0, false, 1], [.37, 0, 0, false, 1], [1, 0, 0, false, 1],
      [2, 0, 0, false, 1], [8, 0, 0, false, 1],
      [1.7, 37, 14, true, .31], [2, -75, -22, false, .83],
    ]) {
      object.set({ angle, skewX: skew, flipX, flipY: flipX, opacity, scaleX: 1.8, scaleY: skew ? .93 : 1.8 });
      canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2 + .31, canvas.height / 2 + .67]);
      syncSelectedShapeOutlines();
      const hooked = [object, selectedShapeOutlineHelpers.get(object)?.clipPath].filter(Boolean);
      const expectedShape = JSON.stringify(snapshotShapes());
      const draws = [], times = [];
      for (const baseline of [true, false]) {
        for (const item of hooked) {
          item._renderPathCommands = baseline ? fabric.Path.prototype._renderPathCommands : renderNativeTriangleFill;
          item.dirty = true;
        }
        const helper = selectedShapeOutlineHelpers.get(object);
        if (helper) helper.dirty = true;
        const start = performance.now();
        canvas.renderAll();
        times.push(performance.now() - start);
        draws.push(read());
      }
      let changed = 0;
      for (let i = 0; i < draws[0].length; i++) if (draws[0][i] !== draws[1][i]) changed++;
      if (changed || JSON.stringify(snapshotShapes()) !== expectedShape || JSON.stringify(object.path) !== geometry) {
        throw Error(`Shape 9 zoom ${zoom}: ${changed} changed channels, or changed geometry/export`);
      }
      rows.push({ zoom, angle, skew, flipX, opacity, changed, baselineMs: times[0], fixedMs: times[1] });
    }
    const masks = [];
    object.set({ angle: 0, skewX: 0, flipX: false, flipY: false, opacity: 1, scaleX: 1, scaleY: 1 });
    for (const helper of [makeMaskCutoutForObject(object), makeMaskOutlineForObject(object)]) {
      const surface = document.createElement('canvas'); surface.width = surface.height = 512;
      const ctx = surface.getContext('2d', { willReadFrequently: true });
      const render = helper._render, commands = helper._renderPathCommands;
      for (const scale of [.4, 1.2, 2]) {
        helper.set({ scaleX: scale, scaleY: scale * .8 });
        const draws = [];
        for (const baseline of [true, false]) {
          ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, 512, 512);
          ctx.fillStyle = '#abcdef'; ctx.fillRect(0, 0, 512, 512);
          ctx.translate(256, 256); ctx.scale(helper.scaleX, helper.scaleY);
          helper._render = baseline ? fabric.Path.prototype._render : render;
          helper._renderPathCommands = baseline ? fabric.Path.prototype._renderPathCommands : commands;
          helper._render(ctx);
          draws.push(ctx.getImageData(0, 0, 512, 512).data);
        }
        const changed = draws[0].reduce((n, value, i) => n + (value !== draws[1][i]), 0);
        const maxDelta = draws[0].reduce((n, value, i) => Math.max(n, Math.abs(value - draws[1][i])), 0);
        masks.push({ outline: !!helper.kloudyMaskOutline, scale, changed, maxDelta });
      }
      discardFabricObject(helper); surface.width = surface.height = 1;
    }
    return { factories, rows, masks, exactGeometry: true, exactExport: true };
  });
  save('shape9-pixels.json', pixels);
  // Cutout/artwork pixels are exact. The existing Path2D red guide uses a
  // float32 scaled stroke: allow only tiny edge-AA differences, never geometry loss.
  if (pixels.masks.some(row => row.outline ? row.changed > 104 || row.maxDelta > 16 : row.changed !== 0)) {
    throw Error(`Mask guide fidelity exceeded its bound: ${JSON.stringify(pixels.masks)}`);
  }
  const gestures = [];
  for (const count of [1, 300]) {
    await load(count);
    await page.locator('[data-tool-mode="select"]').click();
    for (const mode of ['move', 'resize', 'skew']) {
      const start = await page.evaluate(mode => {
        const object = vinylObjects().at(-1);
        object.setCoords(); styleActiveTransformControls(); canvas.renderAll();
        const rect = canvas.upperCanvasEl.getBoundingClientRect();
        let point = object.oCoords.br;
        if (mode === 'move') {
          const source = document.createElement('canvas'); source.width = canvas.width; source.height = canvas.height;
          const ctx = source.getContext('2d', { willReadFrequently: true });
          ctx.transform(...canvas.viewportTransform); object.render(ctx);
          const data = ctx.getImageData(0, 0, source.width, source.height).data;
          point = null;
          for (let y = 60; y < source.height - 60 && !point; y += 5) {
            for (let x = 60; x < source.width - 60; x += 5) {
              if (data[(y * source.width + x) * 4 + 3] > 180) { point = { x, y }; break; }
            }
          }
          source.width = source.height = 1;
          if (!point) throw Error('No visible pixel for pointer drag');
        }
        return { x: point.x + rect.left, y: point.y + rect.top,
          before: JSON.stringify(snapshotShapes()), shape: objectToShape(object) };
      }, mode);
      const begin = Date.now();
      await page.mouse.move(start.x, start.y);
      if (mode === 'skew') await page.keyboard.down('Shift');
      try {
        await page.mouse.down();
        await page.mouse.move(start.x + 28, start.y + (mode === 'skew' ? 0 : 19), { steps: 10 });
        await page.mouse.up();
      } finally {
        await page.mouse.up();
        if (mode === 'skew') await page.keyboard.up('Shift');
      }
      const elapsed = Date.now() - begin;
      const after = await page.evaluate(() => JSON.stringify(snapshotShapes()));
      if (after === start.before) throw Error(`${count} layers/${mode}: pointer gesture changed nothing`);
      const beforeShapes = JSON.parse(start.before), afterShapes = JSON.parse(after);
      if (JSON.stringify(beforeShapes.slice(0, -1)) !== JSON.stringify(afterShapes.slice(0, -1))) throw Error('Unrelated layers changed');
      if (mode === 'skew' && afterShapes.at(-1).data[5] === beforeShapes.at(-1).data[5]) throw Error('Shift drag did not skew');
      await page.locator('#undoBtn').click();
      await page.waitForFunction(expected => JSON.stringify(snapshotShapes()) === expected, start.before);
      await page.locator('#redoBtn').click();
      await page.waitForFunction(expected => JSON.stringify(snapshotShapes()) === expected, after);
      await page.locator('#undoBtn').click();
      await page.waitForFunction(expected => JSON.stringify(snapshotShapes()) === expected, start.before);
      gestures.push({ count, mode, elapsed, exactUndoRedo: true });
      save('shape9-gestures.json', gestures);
    }
  }
  await load();
  const original = await page.evaluate(() => JSON.stringify(snapshotShapes()[0]));
  await page.locator('#quickDuplicateLayer').click();
  await page.waitForFunction(() => vinylObjects().length === 2 && !editorCommands.busy);
  const duplicatePaths = await page.evaluate(() => {
    const objects = vinylObjects();
    if (objects[0].path !== objects[1].path || !Object.isFrozen(objects[0].path)) throw Error('Duplicated mesh is not immutable/shared');
    return JSON.stringify(objects[0].path);
  });
  await page.locator('#quickColorSwatch').click();
  await page.locator('#dialogColorPicker').evaluate(input => {
    input.value = '#12ab34'; input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await page.locator('#closeColorDialog').click();
  await page.waitForFunction(() => JSON.stringify(objectToShape(selectedVinylObjects()[0]).color) === JSON.stringify([18, 171, 52, 255]));
  const duplicate = await page.evaluate(({ original, duplicatePaths }) => {
    const unchanged = vinylObjects().find(o => o.kloudy.editor_id === JSON.parse(original).editor_id);
    if (JSON.stringify(objectToShape(unchanged, { includeEditorMeta: true })) !== original
      || vinylObjects().some(o => JSON.stringify(o.path) !== duplicatePaths)) throw Error('Duplicate editing changed original data or shared geometry');
    return { independentRecolor: true, immutableGeometry: true };
  }, { original, duplicatePaths });
  const saved = await page.evaluate(async () => {
    currentProjectName = 'Community 4 Shape 9 regression';
    await saveProject();
    if (documentDirty) throw Error('Project did not save');
    return JSON.stringify(snapshotShapes());
  });
  const processInfo = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
  const projectDir = path.join(processInfo.profile, 'projects');
  const project = fs.readdirSync(projectDir).find(name => name.startsWith('Community 4 Shape 9 regression') && name.endsWith('.json'));
  if (!project || JSON.stringify(JSON.parse(fs.readFileSync(path.join(projectDir, project), 'utf8')).shapes) !== saved) {
    throw Error('Saved shape data differs');
  }
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()));
  await page.evaluate(() => openProjectBrowser());
  await page.locator('#projectBrowserEntries button').filter({ hasText: 'Community 4 Shape 9 regression' }).dblclick();
  await page.waitForFunction(expected => !editorCommands.busy && JSON.stringify(snapshotShapes()) === expected, saved);
  await page.screenshot({ path: path.join(output, 'shape9-reopened.png') });
  const result = { pixels, gestures, duplicate, recolor: true, exactSavedFile: true, exactProjectReopen: true };
  save('shape9-regression.json', result);
  return result;
}
