async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [70 + index % 160, 130, 220, 255],
      data: [-850 + (index % 60) * 28, 620 - Math.floor(index / 60) * 25, 0.2, 0.2, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    const loadStarted = performance.now();
    await loadPayload({ shapes });
    const loadMs = performance.now() - loadStarted;
    const firstDrawStarted = performance.now();
    hybridRenderNow();
    const firstInteractionDrawMs = performance.now() - firstDrawStarted;
    return {
      loadMs,
      firstInteractionDrawMs,
      pipelineWarmed: Boolean(hybridRenderer?.pipelineWarmed),
      layers: vinylObjects().length,
    };
  });
}
