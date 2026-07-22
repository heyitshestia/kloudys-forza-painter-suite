async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const layerCount = 3000;
    const shapes = Array.from({ length: layerCount }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [
        48 + (index * 29) % 208,
        48 + (index * 47) % 208,
        48 + (index * 71) % 208,
        255,
      ],
      data: [
        -960 + (index % 60) * 32,
        -784 + Math.floor(index / 60) * 32,
        0.22 + (index % 5) * 0.025,
        0.22 + (index % 7) * 0.02,
        index % 24 * 15,
        0,
        0,
      ],
      editor_group_id: Math.floor(index / 20) % 3 === 0 ? `bench-${Math.floor(index / 20)}` : null,
      editor_group_name: Math.floor(index / 20) % 3 === 0 ? `Benchmark ${Math.floor(index / 20)}` : null,
    }));

    const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
    const timed = async (callback) => {
      const start = performance.now();
      const result = await callback();
      return { ms: performance.now() - start, result };
    };
    const percentile = (values, fraction) => {
      if (!values.length) return 0;
      const ordered = values.slice().sort((a, b) => a - b);
      return ordered[Math.min(ordered.length - 1, Math.floor(ordered.length * fraction))];
    };

    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    clearAutosave();
    const load = await timed(() => loadPayload({ shapes }));
    await frame();
    await frame();

    const refresh = await timed(() => refreshLayers());
    const snapshot = await timed(() => snapshotEditorState());
    const coordinateSync = await timed(() => syncCanvasObjectCoords());

    const originalViewport = canvas.viewportTransform.slice();
    const renderDurations = [];
    const frameDurations = [];
    let previousFrame = performance.now();
    for (let index = 0; index < 120; index += 1) {
      canvas.viewportTransform[4] += index % 2 ? -1.5 : 1.5;
      const renderStart = performance.now();
      hybridRenderNow();
      renderDurations.push(performance.now() - renderStart);
      await frame();
      const now = performance.now();
      frameDurations.push(now - previousFrame);
      previousFrame = now;
    }
    canvas.setViewportTransform(originalViewport);
    endHybridRenderNow();

    const historyEstimate = historyStorageEstimate();
    return {
      layerCount,
      loadMs: load.ms,
      refreshLayersMs: refresh.ms,
      snapshotMs: snapshot.ms,
      coordinateSyncMs: coordinateSync.ms,
      historyEntries: history.length,
      historyBytes: historyEstimate.bytes,
      historyUniqueShapes: historyEstimate.uniqueShapes,
      canvasObjects: canvas.getObjects().length,
      layerDomElements: document.querySelectorAll("#layers *").length,
      hybridAvailable: hybridShouldUse(vinylObjects()),
      hybridDrawAverageMs: renderDurations.reduce((sum, value) => sum + value, 0) / renderDurations.length,
      hybridDrawP95Ms: percentile(renderDurations, 0.95),
      frameAverageMs: frameDurations.reduce((sum, value) => sum + value, 0) / frameDurations.length,
      frameP95Ms: percentile(frameDurations, 0.95),
      heapBytes: performance.memory?.usedJSHeapSize || null,
    };
  });
}
