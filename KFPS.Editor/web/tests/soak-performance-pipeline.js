async (page, options = {}) => {
  page.setDefaultTimeout(180000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const cdp = await page.context().newCDPSession(page);
  const loadReference = async size => {
    if (options.mode !== "large") return page.evaluate(size => window.soakReference(size), size);
    const { root } = await cdp.send("DOM.getDocument");
    const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector: "#overlayInput" });
    await cdp.send("DOM.setFileInputFiles", { nodeId, files: [`${options.fixtures}/reference-${size}.png`] });
    await page.waitForFunction(size => editorReference.source?.fileName === `reference-${size}.png`, size);
  };
  const samples = [], checkpoints = [];
  let operations = 0;
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => {
      const gradient = i % 8 === 0, mask = i > 0 && i % 17 === 0;
      return { type: gradient ? 1048777 : 1048677, resource_family: gradient ? "Gradient_Shapes" : "Primitives", resource_index: 1,
        type_word: gradient ? 201 : 101, color: [50 + i % 170, 120, 200, 220], mask,
        data: [-720 + i % 60 * 24, 600 - Math.floor(i / 60) * 24, .18, .18, 0, 0, mask ? 1 : 0],
        editor_group_id: "group-" + Math.floor(i / 20), editor_group_name: "Soak group " + Math.floor(i / 20) };
    }) });
    fitDesignView();
    window.soakLongTasks = [];
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) if (window.soakLongTasks.length < 20000) window.soakLongTasks.push(entry.duration);
    }).observe({ type: "longtask" });
    window.soakReference = async size => {
      const source = document.createElement("canvas"); source.width = source.height = size;
      const context = source.getContext("2d");
      context.fillStyle = "#a4bdca"; context.fillRect(0, 0, size, size);
      context.fillStyle = "#e98eaa"; context.fillRect(0, 0, size / 2, size / 2);
      editorReference.removeOverlay();
      await editorReference.loadOverlayImageFromUrl(source.toDataURL(), `soak-reference-${size}.png`);
      source.width = source.height = 1;
    };
  });
  await loadReference(options.mode === "large" ? 49 : 2048);
  await page.evaluate(async () => {
    currentProjectName = "Performance Soak";
    await saveProject();
  });
  const started = Date.now();
  let nextCheckpoint = 0;
  while (Date.now() - started < 21 * 60 * 1000) {
    const count = operations;
    const elapsed = await page.evaluate(async count => {
      const objects = vinylObjects();
      const start = performance.now();
      const index = (count * 19) % 2800;
      const size = count % 10 === 0 ? 1000 : count % 5 === 0 ? 40 : 1;
      selectObjects(objects.slice(index, Math.min(3000, index + size)), "sustained edit");
      nudgeSelected(count % 2 ? -1 : 1, 0);
      flushPendingNudgeHistory();
      if (count % 25 === 0) { await undo(); await redo(); }
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      if (editorHistory.entries.length > 80 || vinylObjects().length !== 3000) throw new Error("Sustained edit changed layer/history bounds");
      return performance.now() - start;
    }, count);
    samples.push(elapsed);
    operations++;
    if (Date.now() - started >= nextCheckpoint) {
      const minute = Math.floor((Date.now() - started) / 60000);
      if (minute > 0 && minute % 4 === 0) {
        await page.evaluate(async minute => {
          const before = JSON.stringify(snapshotShapes());
          await saveProject();
          if (documentDirty) throw new Error("Sustained save left an unchanged document dirty");
          const response = await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent("Performance Soak.fabric-project.json")}`, { cache: "no-store" });
          const data = await response.json();
          if (!response.ok || JSON.stringify(data.payload?.shapes) !== before) throw new Error("Sustained project save changed artwork");
        }, minute);
        await loadReference(options.mode === "large" ? (minute % 8 === 0 ? 35 : 49) : (minute % 8 === 0 ? 4096 : 2048));
      }
      const state = await page.evaluate(async () => {
        nudgeSelected(1, 0); flushPendingNudgeHistory();
        await flushPendingAutosave();
        const recovery = await readAutosavePayload();
        if (JSON.stringify(recovery?.shapes) !== JSON.stringify(snapshotShapes())) throw new Error("Sustained recovery does not match artwork");
        return { history: historyStorageEstimate(), historyEntries: editorHistory.entries.length, layers: vinylObjects().length,
          masks: maskPreviewOutlines.size, selectionHelpers: selectedShapeOutlineHelpers.size,
          referencePixels: (editorReference.sampler?.width || 0) * (editorReference.sampler?.height || 0),
          longTasks: window.soakLongTasks.length, maxLongTaskMs: Math.max(0, ...window.soakLongTasks), recovery: editorRecovery.status.state };
      });
      const beforeGc = await cdp.send("Runtime.getHeapUsage");
      let afterGc = null;
      if (minute % 5 === 0) { await cdp.send("HeapProfiler.collectGarbage"); afterGc = await cdp.send("Runtime.getHeapUsage"); }
      const dom = await cdp.send("Memory.getDOMCounters");
      const recent = samples.slice(-120).sort((a, b) => a - b);
      const checkpoint = { minute, seconds: (Date.now() - started) / 1000, operations, medianRecentMs: recent[Math.floor(recent.length / 2)], maxRecentMs: recent.at(-1), beforeGc, afterGc, dom, state };
      checkpoints.push(checkpoint);
      console.log(JSON.stringify({ soakCheckpoint: checkpoint }));
      nextCheckpoint = (minute + 1) * 60000;
    }
    await page.waitForTimeout(350);
  }
  const reopened = await page.evaluate(async () => {
    const before = JSON.stringify(snapshotShapes());
    await saveProject();
    await flushPendingAutosave();
    const response = await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent("Performance Soak.fabric-project.json")}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error("Final project readback failed");
    await loadProjectPayload(data.payload, "Performance Soak");
    if (JSON.stringify(snapshotShapes()) !== before) throw new Error("Final project reopen changed artwork");
    return true;
  });
  await cdp.send("HeapProfiler.collectGarbage");
  const finalHeap = await cdp.send("Runtime.getHeapUsage");
  await page.screenshot({ path: "sustained-editor.png" });
  await cdp.detach();
  return { seconds: (Date.now() - started) / 1000, operations, checkpoints, finalHeap, reopened };
}
