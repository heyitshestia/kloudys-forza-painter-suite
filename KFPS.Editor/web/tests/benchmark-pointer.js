async (page) => {
  page.setDefaultTimeout(180000);
  await page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [100 + index % 120, 150, 220, 255],
      data: [-850 + (index % 60) * 29, 600 - Math.floor(index / 60) * 25, 0.24, 0.24, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    await loadPayload({ shapes });
    window.__pointerBenchmark = [];
    const original = canvas.findTarget.bind(canvas);
    window.__pointerBenchmarkOriginal = original;
    canvas.findTarget = function measuredFindTarget(event, skipGroup) {
      const start = performance.now();
      const result = original(event, skipGroup);
      window.__pointerBenchmark.push(performance.now() - start);
      return result;
    };
  });
  const box = await page.locator(".upper-canvas").boundingBox();
  for (let index = 0; index < 180; index += 1) {
    const x = box.x + 10 + ((index * 37) % Math.max(20, box.width - 20));
    const y = box.y + 10 + ((index * 53) % Math.max(20, box.height - 20));
    await page.mouse.move(x, y);
  }
  return page.evaluate(() => {
    const samples = window.__pointerBenchmark || [];
    const ordered = samples.slice().sort((a, b) => a - b);
    if (window.__pointerBenchmarkOriginal) {
      canvas.findTarget = window.__pointerBenchmarkOriginal;
      delete window.__pointerBenchmarkOriginal;
    }
    return {
      samples: samples.length,
      averageMs: samples.reduce((total, value) => total + value, 0) / Math.max(1, samples.length),
      p95Ms: ordered[Math.min(ordered.length - 1, Math.floor(ordered.length * 0.95))] || 0,
      maxMs: ordered[ordered.length - 1] || 0,
      canvasPerPixelTargetFind: canvas.perPixelTargetFind,
    };
  });
}
