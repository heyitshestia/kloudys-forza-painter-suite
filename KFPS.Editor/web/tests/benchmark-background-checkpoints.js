async (page, options) => {
  const referenceFile = options.referenceFile || "reference-49.png";
  const cdp = await page.context().newCDPSession(page);
  await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
      type: 1048677, color: [70, 140, 210, 255],
      data: [i % 60 * 24 - 720, Math.floor(i / 60) * 24 - 600, .1, .1, 0, 0, 0],
      editor_group_id: "group" + Math.floor(i / 40),
    })) });
    await flushPendingAutosave();
    selectObjects(vinylObjects().slice(0, 40), "background benchmark");
    window.checkpointProbe = { tasks: [], frames: [] };
    new PerformanceObserver(list => checkpointProbe.tasks.push(...list.getEntries().map(item => ({ time: item.startTime, duration: item.duration })))).observe({ type: "longtask" });
    let previous = performance.now();
    const frame = now => { checkpointProbe.frames.push({ time: now, gap: now - previous }); previous = now; requestAnimationFrame(frame); };
    requestAnimationFrame(frame);
  });
  const rows = [];
  const timed = async (label, action) => {
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const start = await page.evaluate(() => performance.now());
    const detail = await action();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const row = await page.evaluate(({ start, label }) => {
      const frames = checkpointProbe.frames.filter(item => item.time > start).map(item => item.gap).sort((a, b) => a - b);
      const tasks = checkpointProbe.tasks.filter(item => item.time >= start).map(item => item.duration);
      return { label, ms: performance.now() - start, maxFrameMs: Math.max(0, ...frames), p95FrameMs: frames[Math.floor(frames.length * .95)] || 0, maxTaskMs: Math.max(0, ...tasks), longTasks: tasks.length };
    }, { start, label });
    rows.push({ ...row, detail });
  };
  try {
    // Native local file selection avoids Playwright's large base64 transport
    // injection being misreported as application image-load work.
    const { root } = await cdp.send("DOM.getDocument");
    const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector: "#overlayInput" });
    await timed("native-reference-load", async () => {
      await cdp.send("DOM.setFileInputFiles", { nodeId, files: [`${options.fixtures}/${referenceFile}`] });
      await page.waitForFunction(name => editorReference.source?.fileName === name, referenceFile);
      return page.evaluate(() => ({ bytes: editorReference.source.dataUrl.length, pixels: editorReference.sampler.width * editorReference.sampler.height }));
    });
    await timed("first-reference-checkpoint", () => page.evaluate(async () => {
      await flushPendingAutosave();
      if (!editorRecovery.status.serverOk) throw new Error("Initial reference checkpoint was not acknowledged");
    }));
    for (const throttle of [1, 4]) {
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: throttle });
      // Let the previous interaction's 260 ms GPU/Fabric handoff settle so this
      // sample measures background work, not an unrelated pending repaint.
      await page.waitForTimeout(1000);
      await timed(`background-only-cpu${throttle}`, () => page.evaluate(async () => {
        const started = performance.now();
        writeAutosavePayload(autosavePayloadFromState(currentHistoryState()));
        await flushPendingAutosave();
        if (!editorRecovery.status.serverOk) throw new Error("Background-only checkpoint failed");
        return { acknowledgementMs: performance.now() - started };
      }));
      for (let iteration = 0; iteration < 3; iteration++) {
        await timed(`steady-checkpoint-cpu${throttle}-${iteration}`, () => page.evaluate(async () => {
          const started = performance.now();
          nudgeSelected(1, 0); flushPendingNudgeHistory();
          await flushPendingAutosave();
          if (!editorRecovery.status.serverOk) throw new Error("Background checkpoint failed");
          return { acknowledgementMs: performance.now() - started, browserOk: editorRecovery.status.browserOk };
        }));
      }
    }
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    // Correctness readback stays outside the steady background measurements.
    const exact = await page.evaluate(async () => {
      const recovered = await readAutosavePayload();
      if (JSON.stringify(recovered.shapes) !== JSON.stringify(snapshotShapes()) || recovered.editor_source_overlay.data_url !== editorReference.source.dataUrl) throw new Error("Final checkpoint lost layers or reference bytes");
      return true;
    });
    await cdp.send("HeapProfiler.collectGarbage");
    return { rows, exact, heap: await cdp.send("Runtime.getHeapUsage"), fileInput: "native DOM.setFileInputFiles", throttleCaveat: "CDP throttles renderer, not worker or server" };
  } finally {
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
    await page.evaluate(async () => { editorReference.removeOverlay(); await clearAutosave(); documentDirty = false; });
    await cdp.detach();
  }
}
