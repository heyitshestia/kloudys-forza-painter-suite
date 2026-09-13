async (page) => {
  page.setDefaultTimeout(180000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const cdp = await page.context().newCDPSession(page);
  const results = [];
  await page.evaluate(() => {
    window.pipelineAudit = { calls: {}, times: {}, longest: {}, copies: 0, longTasks: [] };
    for (const name of ["refreshLayers", "exportValidation", "syncMaskPreviewOutlines",
      "syncSelectedShapeOutlines", "captureSharedHistoryState", "pushHistory", "renderHistoryList",
      "syncCanvasObjectCoords", "updateSelectionPanel", "hybridRenderNow", "endHybridRenderNow"]) {
      const original = window[name];
      window[name] = function (...args) {
        const start = performance.now();
        try { return original.apply(this, args); }
        finally {
          const elapsed = performance.now() - start, stats = window.pipelineAudit;
          stats.calls[name] = (stats.calls[name] || 0) + 1;
          stats.times[name] = (stats.times[name] || 0) + elapsed;
          stats.longest[name] = Math.max(stats.longest[name] || 0, elapsed);
        }
      };
    }
    for (const name of ["getObjects", "renderAll", "renderCanvas"]) {
      const original = canvas[name];
      canvas[name] = function (...args) {
        const start = performance.now();
        try {
          const result = original.apply(this, args);
          if (name === "getObjects") window.pipelineAudit.copies += result.length;
          return result;
        } finally {
          const elapsed = performance.now() - start, stats = window.pipelineAudit;
          stats.calls[name] = (stats.calls[name] || 0) + 1;
          stats.times[name] = (stats.times[name] || 0) + elapsed;
          stats.longest[name] = Math.max(stats.longest[name] || 0, elapsed);
        }
      };
    }
    new PerformanceObserver(list => {
      const rows = window.pipelineAudit.longTasks;
      for (const entry of list.getEntries()) if (rows.length < 2000) rows.push(entry.duration);
    }).observe({ type: "longtask" });
  });
  for (const fixture of [
    { name: "primitives", count: 3000, masks: 0, selection: 1, throttle: 1 },
    { name: "dense-masks", count: 3000, masks: 3, selection: 1, throttle: 1 },
    { name: "mixed-gradients", count: 1400, masks: 31, selection: 1, throttle: 1 },
    { name: "bulk-selection", count: 3000, masks: 0, selection: 1000, throttle: 1 },
    { name: "cpu-constrained", count: 3000, masks: 0, selection: 1, throttle: 4 },
  ]) {
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: fixture.throttle });
    const setup = await page.evaluate(async fixture => {
      document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
      await clearAutosave();
      const shapes = Array.from({ length: fixture.count }, (_, index) => {
        const gradient = fixture.name === "mixed-gradients" && index % 4 === 0;
        const mask = fixture.masks > 0 && index > 0 && index % fixture.masks === 0;
        return {
          type: gradient ? 1048777 : 1048677, type_word: gradient ? 201 : 101,
          resource_family: gradient ? "Gradient_Shapes" : "Primitives", resource_index: 1,
          color: [80 + index % 160, 120, 180, 230], mask,
          data: [-720 + (index % 60) * 24, 600 - Math.floor(index / 60) * 24, .18, .18, 0, 0, mask ? 1 : 0],
        };
      });
      const start = performance.now();
      await loadPayload({ shapes });
      fitDesignView();
      const selected = fixture.selection === 1 ? [vinylObjects()[Math.floor(fixture.count / 2) + 1]] : vinylObjects().slice(0, fixture.selection);
      selectObjects(selected, "pipeline benchmark");
      canvas.renderAll();
      return { loadAndSelectMs: performance.now() - start, canvasObjects: canvas.getObjects().length };
    }, fixture);
    await page.waitForTimeout(1400);
    await cdp.send("HeapProfiler.collectGarbage");
    const before = await cdp.send("Runtime.getHeapUsage");
    await page.evaluate(() => Object.assign(window.pipelineAudit, { calls: {}, times: {}, longest: {}, copies: 0, longTasks: [] }));
    const samples = [];
    for (let sample = 0; sample < 8; sample++) {
      if (fixture.selection > 1) {
        samples.push(await page.evaluate(async sample => {
          const started = performance.now();
          nudgeSelected(sample % 2 ? -1 : 1, 0);
          flushPendingNudgeHistory();
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          return performance.now() - started;
        }, sample));
      } else {
        const point = await page.evaluate(() => {
          const p = fabric.util.transformPoint(selectedVinylObjects()[0].getCenterPoint(), canvas.viewportTransform);
          const rect = canvas.upperCanvasEl.getBoundingClientRect();
          return { x: rect.left + p.x, y: rect.top + p.y };
        });
        await page.mouse.move(point.x, point.y);
        await page.mouse.down();
        await page.mouse.move(point.x + (sample % 2 ? -10 : 10), point.y + 5, { steps: 3 });
        await page.evaluate(() => {
          window.pipelineRelease = performance.now();
          window.pipelinePaint = null;
          canvas.once("object:modified", () => requestAnimationFrame(() => requestAnimationFrame(() => {
            window.pipelinePaint = performance.now() - window.pipelineRelease;
          })));
        });
        await page.mouse.up();
        await page.waitForFunction(() => window.pipelinePaint !== null);
        samples.push(await page.evaluate(() => window.pipelinePaint));
      }
      await page.waitForTimeout(200);
    }
    await page.waitForTimeout(1600);
    const stats = await page.evaluate(() => ({ ...window.pipelineAudit, layers: vinylObjects().length, history: historyStorageEstimate(), recovery: editorRecovery.status }));
    await cdp.send("HeapProfiler.collectGarbage");
    const after = await cdp.send("Runtime.getHeapUsage");
    samples.sort((a, b) => a - b);
    results.push({ fixture, setup, samplesMs: samples, medianMs: samples[4], maxMs: samples[7], before, after, stats });
  }
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  await cdp.detach();
  return results;
}
