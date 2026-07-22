async (page) => {
  page.setDefaultTimeout(300000);
  return page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [130, 100 + index % 140, 210, 255],
      data: [-850 + (index % 60) * 28, 620 - Math.floor(index / 60) * 25, 0.2, 0.2, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    await loadPayload({ shapes });
    const firstId = vinylObjects()[0].kloudy.editor_id;
    const originalLeft = vinylObjects()[0].left;
    const selectStart = performance.now();
    selectObjects(vinylObjects(), "3,000-layer benchmark");
    const selectMs = performance.now() - selectStart;
    const nudgeSamples = [];
    for (let index = 0; index < 40; index += 1) {
      const started = performance.now();
      nudgeSelected(1, 0);
      nudgeSamples.push(performance.now() - started);
    }
    const movedLeft = vinylObjects().find((object) => object.kloudy.editor_id === firstId).calcTransformMatrix()[4];
    await undo();
    const restored = vinylObjects().find((object) => object.kloudy.editor_id === firstId);
    const ordered = nudgeSamples.slice().sort((a, b) => a - b);
    return {
      layers: vinylObjects().length,
      selectMs,
      nudgeAverageMs: nudgeSamples.reduce((sum, value) => sum + value, 0) / nudgeSamples.length,
      nudgeP95Ms: ordered[Math.floor(ordered.length * 0.95)],
      movedBy: movedLeft - originalLeft,
      restored: Math.abs(restored.calcTransformMatrix()[4] - originalLeft) < 0.001,
      historyEntries: history.length,
    };
  });
}
