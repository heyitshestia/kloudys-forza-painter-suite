async (page, options) => {
  page.setDefaultTimeout(180000);
  page.setDefaultNavigationTimeout(30000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const cdp = await page.context().newCDPSession(page);
  const results = [];
  const sizes = options.mode === "large" ? [35, 49] : [0, 18];
  await page.evaluate(() => {
    window.storageProbe = { longTasks: [], frames: [] };
    const observer = new PerformanceObserver(list => {
      storageProbe.longTasks.push(...list.getEntries().map(item => ({ start: item.startTime, duration: item.duration })));
    });
    observer.observe({ type: "longtask" });
    let previous = performance.now();
    const frame = now => { storageProbe.frames.push({ time: now, gap: now - previous }); previous = now; requestAnimationFrame(frame); };
    requestAnimationFrame(frame);
  });
  const timed = async (label, action) => {
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const before = await page.evaluate(() => performance.now());
    const started = Date.now();
    const detail = await action();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const metrics = await page.evaluate(start => {
      const gaps = storageProbe.frames.filter(item => item.time >= start).map(item => item.gap).sort((a, b) => a - b);
      const tasks = storageProbe.longTasks.filter(item => item.start >= start).map(item => item.duration);
      return { pageMs: performance.now() - start, maxFrameGapMs: Math.max(0, ...gaps),
        frameGapP95Ms: gaps[Math.floor(gaps.length * .95)] || 0, longTasks: tasks.length, maxLongTaskMs: Math.max(0, ...tasks) };
    }, before);
    return { label, wallMs: Date.now() - started, ...metrics, detail };
  };
  try {
    for (const size of sizes) {
      await page.evaluate(async () => {
        editorRenderer.endHybridRenderNow();
        await clearAutosave();
        await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
          type: 1048677, color: [70 + i % 160, 120, 170, 255],
          data: [-720 + i % 60 * 24, 600 - Math.floor(i / 60) * 24, .15, .15, 0, 0, 0],
          editor_group_id: "g" + Math.floor(i / 20), editor_group_name: "Group " + Math.floor(i / 20),
        })) });
        fitDesignView();
      });
      await cdp.send("HeapProfiler.collectGarbage");
      const beforeHeap = await cdp.send("Runtime.getHeapUsage");
      const operations = [];
      if (size) operations.push(await timed("reference-load", async () => {
        await page.locator("#overlayInput").setInputFiles(`${options.fixtures}/reference-${size}.png`);
        await page.waitForFunction(size => editorReference.source?.fileName === `reference-${size}.png`, size);
        return page.evaluate(() => ({ pixels: editorReference.sampler.width * editorReference.sampler.height, sourceBytes: editorReference.source.dataUrl.length }));
      }));
      const projectBytes = await page.evaluate(() => new Blob([JSON.stringify(editableProjectPayload("Storage benchmark"))]).size);
      for (let repeat = 0; repeat < 3; repeat++) {
        operations.push(await timed("save", () => page.evaluate(async ({ size, repeat }) => {
          currentProjectName = `Storage ${size}`;
          await saveProject();
          if (documentDirty) throw new Error("Storage benchmark save failed");
          return { repeat };
        }, { size, repeat })));
        operations.push(await timed("continuous-edit-and-recovery", () => page.evaluate(async repeat => {
          const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
          const source = editorReference.source?.dataUrl;
          selectObjects(vinylObjects().slice(repeat * 40, repeat * 40 + 40), "storage benchmark");
          for (let i = 0; i < 30; i++) { nudgeSelected(1, 0); await sleep(80); }
          flushPendingNudgeHistory();
          await flushPendingAutosave();
          if (!editorRecovery.status.serverOk) throw new Error("Storage benchmark recovery failed: " + editorRecovery.status.error);
          const saved = await readAutosavePayload();
          if (saved.editor_source_overlay?.data_url !== source || JSON.stringify(saved.shapes) !== JSON.stringify(snapshotShapes())) throw new Error("Recovery readback changed artwork/source");
          return { repeat, recovery: editorRecovery.status.state, browserFallback: editorRecovery.status.browserOk };
        }, repeat)));
      }
      operations.push(await timed("project-reopen", () => page.evaluate(async size => {
        await saveProject();
        const before = JSON.stringify(editorReference.sourceOverlayProjectState());
        const shapes = JSON.stringify(snapshotShapes());
        const response = await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(`Storage ${size}.fabric-project.json`)}`, { cache: "no-store" });
        const data = await response.json();
        await loadProjectPayload(data.payload, `Storage ${size}`);
        if (before !== JSON.stringify(editorReference.sourceOverlayProjectState()) || shapes !== JSON.stringify(snapshotShapes())) throw new Error("Saved project did not reopen exactly");
        return { exact: true };
      }, size)));
      await cdp.send("HeapProfiler.collectGarbage");
      const retained = await cdp.send("Runtime.getHeapUsage");
      if (size === sizes.at(-1)) {
        await page.evaluate(() => selectObjects(vinylObjects().slice(0, 40), "throttled storage benchmark"));
        await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
        operations.push(await timed("recovery-cpu4x", () => page.evaluate(async () => {
          nudgeSelected(1, 0); flushPendingNudgeHistory(); await flushPendingAutosave();
          if (!editorRecovery.status.serverOk) throw new Error("Throttled recovery failed");
        })));
        await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
      }
      const record = { size, projectBytes, beforeHeap, retained, operations };
      results.push(record);
      console.log(JSON.stringify({ storageCase: record }));
      await page.screenshot({ path: `storage-${size}.png` });
      await page.evaluate(async () => { editorRenderer.endHybridRenderNow(); editorReference.removeOverlay(); await clearAutosave(); documentDirty = false; });
      await cdp.send("HeapProfiler.collectGarbage");
      record.afterRemoval = await cdp.send("Runtime.getHeapUsage");
    }
  } finally {
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    await cdp.detach();
  }
  return results;
}
