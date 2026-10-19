async (page, options = {}) => {
  const save = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2));
  await page.evaluate(async primaryMaskResource => {
    const resources = [['Primitives', 1], ['Gradient_Shapes', 1], primaryMaskResource, ['Tears', 39]];
    await loadPayload({ shapes: resources.map(([family, slot], i) => ({
      type: editorCatalog.resourceToTypeCode(family, slot), resource_family: family, resource_index: slot,
      editor_id: `mask-gate-${i}`, color: [90 + i * 20, 130, 190, i === 1 ? 117 : 255], mask: i >= 2,
      data: [i === 3 ? 110 : 0, i === 3 ? 35 : 0, i === 0 ? 3 : .4, i === 0 ? 2 : .4, i === 2 ? 68 : 0, 0, i >= 2 ? 1 : 0],
    })) });
    canvas.cancelRequestedRender();
    window.maskGateRows = [];
    window.maskGateCompare = label => {
      const helpers = canvas.getObjects().filter(o => o.kloudyMaskOutline);
      const serialized = JSON.stringify(snapshotShapes());
      const read = () => canvas.contextContainer.getImageData(0, 0, canvas.lowerCanvasEl.width, canvas.lowerCanvasEl.height).data;
      const compare = (a, b) => {
        let channels = 0, maxDelta = 0;
        const pixels = new Set();
        for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) {
          channels++; pixels.add(Math.floor(i / 4)); maxDelta = Math.max(maxDelta, Math.abs(a[i] - b[i]));
        }
        return { channels, pixels: pixels.size, maxDelta };
      };
      const guideSignal = (baseline, candidate, withoutGuides) => {
        const width = canvas.lowerCanvasEl.width, height = canvas.lowerCanvasEl.height;
        const footprint = new Uint8Array(width * height);
        let baselinePixels = 0, baselineSignal = 0, candidateSignal = 0;
        let strongPixels = 0, lostStrongPixels = 0, errorSignal = 0, outsideBoundary = 0;
        for (let pixel = 0; pixel < footprint.length; pixel++) {
          let before = 0, after = 0;
          for (let channel = 0; channel < 4; channel++) {
            const index = pixel * 4 + channel;
            before = Math.max(before, Math.abs(baseline[index] - withoutGuides[index]));
            after = Math.max(after, Math.abs(candidate[index] - withoutGuides[index]));
            baselineSignal += Math.abs(baseline[index] - withoutGuides[index]);
            candidateSignal += Math.abs(candidate[index] - withoutGuides[index]);
            errorSignal += Math.abs(baseline[index] - candidate[index]);
          }
          if (before) { footprint[pixel] = 1; baselinePixels++; }
          if (before >= 64) { strongPixels++; if (after < before / 2) lostStrongPixels++; }
        }
        for (let pixel = 0; pixel < footprint.length; pixel++) {
          const index = pixel * 4;
          if (baseline.subarray(index, index + 4).every((value, channel) => value === candidate[index + channel])) continue;
          const x = pixel % width, y = Math.floor(pixel / width);
          let nearGuide = false;
          for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
            if (x + dx >= 0 && x + dx < width && y + dy >= 0 && y + dy < height
              && footprint[(y + dy) * width + x + dx]) nearGuide = true;
          }
          if (!nearGuide) outsideBoundary++;
        }
        const guide = compare(baseline, candidate);
        const errorFraction = errorSignal / Math.max(1, baselineSignal);
        const lostStrongFraction = lostStrongPixels / Math.max(1, strongPixels);
        return { baselinePixels, baselineSignal, candidateSignal, strongPixels, lostStrongPixels,
          errorFraction, lostStrongFraction, outsideBoundary, ...guide,
          passed: baselinePixels > 0 && strongPixels > 0 && outsideBoundary === 0
            && errorFraction <= .02 && lostStrongFraction <= .001 && guide.pixels <= baselinePixels * .25 };
      };
      let baseline, baselineMs;
      const product = helpers.map(o => o._render);
      try {
        helpers.forEach(o => { o._render = fabric.Path.prototype._render; });
        const started = performance.now(); canvas.renderAll(); baselineMs = performance.now() - started; baseline = read();
      } finally { helpers.forEach((o, i) => { o._render = product[i]; }); }
      const started = performance.now(); canvas.renderAll(); const productMs = performance.now() - started;
      const candidate = read();
      const guide = compare(baseline, candidate);
      // Only UI antialiasing is relaxed. Artwork and actual mask cutouts stay exact.
      const visible = helpers.map(o => o.visible);
      let artwork, withoutGuides;
      try {
        helpers.forEach(o => { o.visible = false; o._render = fabric.Path.prototype._render; });
        canvas.renderAll(); const before = read(); withoutGuides = before;
        helpers.forEach((o, i) => { o._render = product[i]; }); canvas.renderAll();
        artwork = compare(before, read());
      } finally { helpers.forEach((o, i) => { o.visible = visible[i]; o._render = product[i]; }); }
      const signal = guideSignal(baseline, candidate, withoutGuides);
      const disabledHelpers = [];
      try {
        for (let index = 0; index < helpers.length; index++) {
          if (!visible[index]) continue;
          helpers[index]._render = () => {};
          canvas.renderAll();
          disabledHelpers.push({ index, ...guideSignal(baseline, read(), withoutGuides) });
          helpers[index]._render = product[index];
        }
      } finally { helpers.forEach((o, i) => { o._render = product[i]; }); }
      if (artwork.channels) throw Error(`${label}: actual artwork changed`);
      if (!signal.passed) throw Error(`${label}: guide signal/boundary failed: ${JSON.stringify(signal)}`);
      if (disabledHelpers.some(row => row.passed)) throw Error(`${label}: disabling a visible guide escaped the signal gate`);
      if (JSON.stringify(snapshotShapes()) !== serialized) throw Error(`${label}: serialization changed`);
      if (!helpers.every(o => o.excludeFromExport) || editableProjectPayload('mask gate').shapes.length !== 4
        || snapshotShapes().length !== 4 || vinylObjects().map(o => objectToShape(o, { includeEditorMeta: false })).length !== 4) {
        throw Error('Mask helpers entered saved/exported artwork');
      }
      const row = { label, baselineMs, productMs, guide, signal, disabledHelpers, artwork, helpersExcluded: true };
      maskGateRows.push(row); return row;
    };
  }, options.primaryMaskResource || ['Racing_Icons', 30]);
  const rows = [];
  for (const zoom of [.25, 1.1581196581196582, 3.25]) {
    rows.push(await page.evaluate(zoom => {
      canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2 + .31, canvas.height / 2 + .67]);
      canvas.cancelRequestedRender(); return maskGateCompare(`zoom-${zoom}`);
    }, zoom));
    save('mask-gates-progress.json', rows);
  }
  rows.push(await page.evaluate(() => {
    canvas.setViewportTransform([1.1, 0, 0, 1.1, canvas.width / 2, canvas.height / 2]);
    const owner = vinylObjects()[2];
    owner.set({ scaleX: .73, scaleY: .41, angle: 37, skewX: 9, flipX: true });
    owner.setCoords(); syncMaskPreviewForTarget(owner); canvas.cancelRequestedRender();
    return maskGateCompare('rotation-skew-flip-nonuniform-scale');
  }));
  save('mask-gates-progress.json', rows);
  rows.push(await page.evaluate(() => {
    vinylObjects()[0].set({ fill: '#8736aa', opacity: .38 });
    vinylObjects()[3].set({ visible: false }); syncMaskPreviewOutlines();
    canvas.cancelRequestedRender(); return maskGateCompare('color-alpha-visibility');
  }));
  save('mask-gates-progress.json', rows);
  const center = await page.evaluate(() => {
    pushHistory('mask render qualification baseline');
    window.maskBefore = JSON.stringify(snapshotShapes());
    const owner = vinylObjects()[2], helper = maskPreviewOutlines.get(owner);
    canvas.setActiveObject(helper); canvas.renderAll();
    const point = fabric.util.transformPoint(helper.getCenterPoint(), canvas.viewportTransform);
    const box = canvas.upperCanvasEl.getBoundingClientRect();
    return { x: box.left + point.x, y: box.top + point.y };
  });
  await page.mouse.move(center.x, center.y); await page.mouse.down();
  await page.mouse.move(center.x + 21, center.y + 15, { steps: 3 }); await page.mouse.up();
  const gesture = await page.evaluate(async () => {
    const after = JSON.stringify(snapshotShapes());
    if (after === maskBefore) throw Error('Real mask-outline drag did not move owner');
    await undo(); if (JSON.stringify(snapshotShapes()) !== maskBefore) throw Error('Mask drag undo mismatch');
    await redo(); if (JSON.stringify(snapshotShapes()) !== after) throw Error('Mask drag redo mismatch');
    return { realMaskDrag: true, exactUndo: true, exactRedo: true };
  });
  const result = { rows, gesture, exactArtwork: true, helpersExcluded: true };
  save('mask-gates.json', result); return result;
}
