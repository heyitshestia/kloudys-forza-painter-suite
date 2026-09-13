async (page,options={}) => {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const trace=await h.monitor(page,output);
  await page.setViewportSize({ width: 1600, height: 1000 });
  const results = [];
  const modifiers = [[], ['Shift'], ['Control'], ['Shift', 'Control']];
  const handles = ['tl', 'tr', 'bl', 'br', 'ml', 'mr', 'mt', 'mb'];
  try {for (const type of (options.types || [1048678, 1048705, 1048706])) {
    await page.evaluate(async type => {
      await loadPayload({ shapes: Array.from({ length: 3000 }, (_, index) => ({
        type: index === 2999 ? type : 1048677, color: [60, 135, 190, 255],
        data: index === 2999 ? [0, 0, 1.4, 1.1, 17, 0, 0] : [-270 + index % 60 * 9, 185 - Math.floor(index / 60) * 7.5, .07, .07, 0, 0, 0],
      })) });
      const source = document.createElement('canvas'); source.width = 6000; source.height = 4000;
      const ctx = source.getContext('2d'); ctx.fillStyle = '#899e9b'; ctx.fillRect(0, 0, source.width, source.height);
      await editorReference.loadOverlayImageFromUrl(source.toDataURL(), 'handle-matrix-reference.png');
      source.width = source.height = 1;
      window.handleMatrixUntouched = JSON.stringify(snapshotShapes().slice(0, -1));
    }, type);
    await page.locator('[data-tool-mode="select"]').click();
    for (const guide of ['none', 'horizontal', 'vertical', 'angled']) {
      await page.evaluate(guide => {
        applySavedGuideState(null);
        guideState.gridEnabled = false;
        guideState.snapCtrlOnly = true;
        guideState.guides = guide === 'none' ? [] : [{ id: 'handle-matrix-guide',
          x1: -400, y1: guide === 'vertical' ? -400 : -100,
          x2: guide === 'vertical' ? -400 : 400,
          y2: guide === 'horizontal' ? -100 : 400, constraint: 'free' }];
        renderGuideObjects();
        setOverlayLayerMode(guide === 'angled' ? 'above' : 'below');
      }, guide);
      for (const keys of modifiers) for (const handle of handles) {
        const label = `${type}/${guide}/${keys.join('+') || 'plain'}/${handle}`;
        await trace.run(label,async()=> {
        const start = await page.evaluate(handle => {
          const target = vinylObjects().at(-1);
          selectObjects([target], 'handle matrix');
          canvas.setViewportTransform([1.5, 0, 0, 1.5, canvas.width / 2, canvas.height / 2]);
          target.setCoords(); styleActiveTransformControls(); canvas.renderAll();
          const coordinate = target.oCoords[handle];
          const rect = canvas.upperCanvasEl.getBoundingClientRect();
          return { x: coordinate.x + rect.left, y: coordinate.y + rect.top,
            before: objectToShape(target), skew: target.skewX || 0 };
        }, handle);
        const dx = handle.includes('l') ? -23 : handle.includes('r') ? 23 : 19;
        const dy = handle.includes('t') ? -18 : handle.includes('b') ? 18 : 14;
        try {
          await page.mouse.move(start.x, start.y);
          for (const key of keys) await page.keyboard.down(key);
          await page.mouse.down();
          await page.mouse.move(start.x + dx, start.y + dy, { steps: 9 });
          await page.mouse.up();
        } finally {
          await page.mouse.up();
          for (const key of keys.toReversed()) await page.keyboard.up(key);
        }
        const result = await page.evaluate(({ before, skew, handle, shift }) => {
          const target = vinylObjects().at(-1);
          const after = objectToShape(target);
          if (JSON.stringify(before) === JSON.stringify(after)) throw Error('Handle drag did not change the shape');
          if (!after.data.every(Number.isFinite) || Math.abs(after.data[2]) < 1e-6 || Math.abs(after.data[3]) < 1e-6) throw Error('Handle produced invalid geometry');
          if (JSON.stringify(snapshotShapes().slice(0, -1)) !== handleMatrixUntouched) throw Error('Handle changed unrelated layers');
          if (shift && ['tl', 'tr', 'bl', 'br'].includes(handle) && Math.abs((target.skewX || 0) - skew) < .01) throw Error('Shift-corner did not skew');
          return { angle: target.angle, skew: target.skewX, data: after.data };
        }, { before: start.before, skew: start.skew, handle, shift: keys.includes('Shift') }).catch(error => { throw Error(`${label}: ${error.message}`); });
        await page.locator('#undoBtn').click();
        await page.waitForFunction(before => JSON.stringify(objectToShape(vinylObjects().at(-1))) === JSON.stringify(before), start.before);
        results.push({ label, ...result, exactUndo: true });
        fs.writeFileSync(path.join(output, 'handle-matrix.json'), JSON.stringify(results, null, 2));
        });
      }
    }
    await page.evaluate(async () => {
      await flushPendingAutosave();
      const stored = await readAutosavePayload();
      if (JSON.stringify(stored.shapes) !== JSON.stringify(snapshotShapes())) throw Error('Handle matrix recovery differs');
    });
  }} finally {await trace.close();}
  if(trace.rows.some(row=>row.after.visible<2700))throw Error('Handle fixture lost dense visibility');
  return { cases: results.length, rows:trace.rows,layers: 3000, types: (options.types || [1048678,1048705,1048706]).length, handles, modifiers, guideStates: 4,
    coverage: 'Real pointer handles and undo under modifier/guide states; not a claim of exact snapping contact for every guide' };
}
