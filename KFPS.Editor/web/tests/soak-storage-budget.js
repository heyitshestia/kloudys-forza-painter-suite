async (page, options) => {
  page.setDefaultTimeout(180000);
  const cdp = await page.context().newCDPSession(page);
  await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
      type: 1048677, color: [80, 150, 220, 255], data: [i % 60 * 22 - 660, Math.floor(i / 60) * 22 - 550, .1, .1, 0, 0, 0],
    })) });
    currentProjectName = "Storage soak";
    fitDesignView();
    window.storageSoak = { maxGap: 0, tasks: 0, maxTask: 0 };
    let previous = performance.now();
    requestAnimationFrame(function sample(now) { storageSoak.maxGap = Math.max(storageSoak.maxGap, now - previous); previous = now; requestAnimationFrame(sample); });
    new PerformanceObserver(list => { for (const entry of list.getEntries()) { storageSoak.tasks++; storageSoak.maxTask = Math.max(storageSoak.maxTask, entry.duration); } }).observe({ type: "longtask" });
  });
  const checkpoints = [];
  const started = Date.now();
  const referenceFiles = options.referenceFiles || ['reference-35.png', 'reference-49.png'];
  const cycles = options.soakCycles || 6;
  const cycleMs = options.cycleMs || 60000;
  for (let cycle = 0; cycle < cycles; cycle++) {
    const referenceFile = referenceFiles[cycle % referenceFiles.length];
    const { root } = await cdp.send('DOM.getDocument');
    const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#overlayInput' });
    await cdp.send('DOM.setFileInputFiles', { nodeId, files: [`${options.fixtures}/${referenceFile}`] });
    await page.waitForFunction(name => editorReference.source?.fileName === name, referenceFile);
    let edits = 0;
    do {
      await page.evaluate(async cycle => {
        selectObjects(vinylObjects().slice(cycle * 30, cycle * 30 + 30), "storage soak");
        for (let i = 0; i < 40; i++) { nudgeSelected(i % 2 ? 1 : -1, 0); await new Promise(resolve => setTimeout(resolve, 60)); }
        nudgeSelected(1, 0); flushPendingNudgeHistory(); await flushPendingAutosave();
        if (!editorRecovery.status.serverOk) throw new Error("Soak recovery failed: " + editorRecovery.status.error);
      }, cycle);
      edits += 41;
    } while (Date.now() - started < (cycle + 1) * cycleMs);
    const state = await page.evaluate(async expectedPixels => {
      const recovery = await readAutosavePayload();
      if (JSON.stringify(recovery.shapes) !== JSON.stringify(snapshotShapes()) || recovery.editor_source_overlay.data_url !== editorReference.source.dataUrl) throw new Error("Soak recovery readback changed data");
      await saveProject();
      if (documentDirty) throw new Error("Soak project save failed");
      // Save starts a clean-session checkpoint independently of its project ACK.
      await flushPendingAutosave();
      const response = await fetch(`${PROJECT_FILE_API}?id=Storage%20soak.fabric-project.json`);
      if (!response.ok) throw new Error("Soak saved project read failed");
      const { payload } = await response.json();
      if (JSON.stringify(payload.shapes) !== JSON.stringify(snapshotShapes()) || payload.editor_source_overlay.data_url !== editorReference.source.dataUrl) throw new Error("Soak saved project changed data");
      const pixels = editorReference.sampler.width * editorReference.sampler.height;
      if (vinylObjects().length !== 3000 || pixels !== expectedPixels || !editorRecovery.status.browserOk || !editorRecovery.status.serverOk) throw new Error("Soak layer, source pixel or checkpoint mismatch: " + JSON.stringify({ layers: vinylObjects().length, pixels, expectedPixels, status: editorRecovery.status }));
      return { ...storageSoak, layers: vinylObjects().length, history: editorHistory.entries.length, pixels, browserFallback: editorRecovery.status.browserOk, projectReadbackExact: true, recoveryReadbackExact: true };
    }, options.expectedPixels || 24000000);
    // Freeze one retained-state sample after each replacement/edit/save cycle.
    await cdp.send("HeapProfiler.collectGarbage");
    checkpoints.push({ cycle, referenceFile, edits, seconds: (Date.now() - started) / 1000, ...state, heap: await cdp.send("Runtime.getHeapUsage") });
    console.log(JSON.stringify({ checkpoint: checkpoints.at(-1) }));
  }
  await page.screenshot({ path: "storage-soak.png" });
  await page.evaluate(async () => { editorReference.removeOverlay(); clearVinylObjects(); resetHistory(); refreshLayers(); await clearAutosave(); documentDirty = false; });
  await cdp.send("HeapProfiler.collectGarbage");
  const cleared = await cdp.send("Runtime.getHeapUsage");
  await cdp.detach();
  return { checkpoints, cleared, seconds: (Date.now() - started) / 1000 };
}
