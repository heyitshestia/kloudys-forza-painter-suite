async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const layerCount = 3000;
    const shapes = Array.from({ length: layerCount }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [90 + index % 140, 120, 180, 255],
      data: [(index % 60) * 24, -Math.floor(index / 60) * 24, 0.2, 0.2, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    clearAutosave();
    await loadPayload({ shapes });
    const target = vinylObjects()[vinylObjects().length - 1];
    const baselineLeft = target.left;
    for (let index = 1; index <= 20; index += 1) {
      target.set({ left: baselineLeft + index * 5 });
      target.setCoords();
      pushHistory(`history benchmark ${index}`);
    }
    const changedLeft = target.left;
    const estimate = historyStorageEstimate();
    const undoStart = performance.now();
    for (let index = 0; index < 20; index += 1) await undo();
    const undoMs = performance.now() - undoStart;
    const afterUndo = vinylObjects().find((object) => object.kloudy.editor_id === target.kloudy.editor_id);
    const undoLeft = afterUndo.left;
    const redoStart = performance.now();
    for (let index = 0; index < 20; index += 1) await redo();
    const redoMs = performance.now() - redoStart;
    const afterRedo = vinylObjects().find((object) => object.kloudy.editor_id === target.kloudy.editor_id);
    return {
      layers: vinylObjects().length,
      historyEntries: history.length,
      estimatedBytes: estimate.bytes,
      uniqueShapes: estimate.uniqueShapes,
      undoMs,
      redoMs,
      baselineRestored: Math.abs(undoLeft - baselineLeft) < 0.001,
      editRestored: Math.abs(afterRedo.left - changedLeft) < 0.001,
      sameFabricObject: afterRedo === target,
      mountedLayerRows: document.querySelectorAll("#layers > li").length,
    };
  });
}
