async (page) => {
  page.setDefaultTimeout(180000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const results = [];
  await page.evaluate(() => {
    window.editBenchmark = { events: [], calls: {}, durations: {} };
    for (const name of ["captureSharedHistoryState", "refreshExportValidation", "pushHistory", "objectToShape"]) {
      const original = window[name];
      window[name] = function (...args) {
        const start = performance.now();
        try { return original.apply(this, args); }
        finally {
          const stats = window.editBenchmark;
          stats.calls[name] = (stats.calls[name] || 0) + 1;
          stats.durations[name] = (stats.durations[name] || 0) + performance.now() - start;
        }
      };
    }
    canvas.on("object:modified", () => {
      const started = window.editBenchmark.releaseAt || performance.now();
      const events = window.editBenchmark.events;
      requestAnimationFrame(() => requestAnimationFrame(() => {
        events.push(performance.now() - started);
      }));
    });
  });
  for (const count of [500, 1400, 3000]) {
    await page.evaluate(async (count) => {
      document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
      clearAutosave();
      const shapes = Array.from({ length: count }, (_, index) => ({
        type: 1048677, type_word: 101, resource_family: "Primitives", resource_index: 1,
        color: [90 + index % 140, 120, 180, 255],
        data: [(index % 60) * 24, -Math.floor(index / 60) * 24, 0.2, 0.2, 0, 0, 0],
      }));
      await loadPayload({ shapes });
      fitDesignView();
      const target = vinylObjects()[Math.floor(count / 2)];
      canvas.setActiveObject(target);
      updateSelectionPanel();
      canvas.requestRenderAll();
      window.editBenchmark.targetId = target.kloudy.editor_id;
      window.editBenchmark.baseline = JSON.stringify(snapshotShapes());
    }, count);
    await page.waitForTimeout(1200);
    await page.evaluate(() => Object.assign(window.editBenchmark, { events: [], calls: {}, durations: {} }));
    for (let sample = 0; sample < 12; sample++) {
      const point = await page.evaluate(() => {
        const target = vinylObjects().find(object => object.kloudy.editor_id === window.editBenchmark.targetId);
        const center = fabric.util.transformPoint(target.getCenterPoint(), canvas.viewportTransform);
        const rect = canvas.upperCanvasEl.getBoundingClientRect();
        return { x: rect.left + center.x, y: rect.top + center.y };
      });
      await page.mouse.move(point.x, point.y);
      await page.mouse.down();
      await page.mouse.move(point.x + (sample % 2 ? -12 : 12), point.y + 8, { steps: 4 });
      await page.evaluate(() => { window.editBenchmark.releaseAt = performance.now(); });
      await page.mouse.up();
      await page.waitForTimeout(180);
    }
    await page.waitForTimeout(2200);
    results.push(await page.evaluate((count) => {
      const values = window.editBenchmark.events.slice().sort((a, b) => a - b);
      if (values.length !== 12) throw new Error(`Expected 12 real drag commits, got ${values.length}`);
      return {
        count, dragCommits: values.length,
        viewport: { width: innerWidth, height: innerHeight },
        releaseToPaintMedianMs: values[Math.floor(values.length / 2)],
        releaseToPaintP95Ms: values[Math.ceil(values.length * .95) - 1],
        calls: window.editBenchmark.calls, durationsMs: window.editBenchmark.durations,
        history: historyStorageEstimate(), layers: vinylObjects().length,
      };
    }, count));
  }
  return results;
}
