async page => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  const cdp = await page.context().newCDPSession(page);
  await page.evaluate(() => {
    window.curveMetrics = null;
    for (const name of ["syncSelectedShapeOutlines", "syncSelectionOutlineHelpers", "syncMaskPreviewOutlines", "pushHistory", "syncCanvasObjectCoords"]) {
      const original = window[name];
      window[name] = function (...args) {
        const start = performance.now();
        try { return original.apply(this, args); }
        finally {
          if (curveMetrics) {
            const entry = curveMetrics.functions[name] ||= { calls: 0, total: 0, max: 0 };
            const ms = performance.now() - start;
            entry.calls++; entry.total += ms; entry.max = Math.max(entry.max, ms);
          }
        }
      };
    }
    const render = fabric.Object.prototype.renderCache;
    fabric.Object.prototype.renderCache = function (...args) {
      const start = performance.now();
      try { return render.apply(this, args); }
      finally { if (curveMetrics) {
        const key = this.kloudySelectionOutlineHelper ? "outline" : this.kloudy ? "shape" : "clip";
        const entry = curveMetrics.cache[key] ||= { calls: 0, total: 0, max: 0 };
        const ms = performance.now() - start;
        entry.calls++; entry.total += ms; entry.max = Math.max(entry.max, ms);
      } }
    };
    new PerformanceObserver(list => {
      if (curveMetrics) curveMetrics.tasks.push(...list.getEntries().map(e => e.duration));
    }).observe({ entryTypes: ["longtask"] });
    let last = performance.now();
    function frame(now) { if (curveMetrics) curveMetrics.frames.push(now - last); last = now; requestAnimationFrame(frame); }
    requestAnimationFrame(frame);
  });
  const results = [];
  for (const [family, index, count, throttle, reference = false] of [
    ["Primitives", 30, 1, 1, true], ["Primitives", 30, 1, 4, true],
    ["Primitives", 30, 1, 1], ["Primitives", 29, 1, 1],
    ["Primitives", 2, 1, 1], ["Community_Vinyls_1", 5, 1, 1],
    ["Primitives", 30, 3000, 1], ["Primitives", 30, 1, 4],
  ]) {
    const fixture = await page.evaluate(async ({family, index, count, reference}) => {
      const shapes = Array.from({length: count}, (_, i) => {
        const f = i ? "Primitives" : family, slot = i ? 1 : index;
        return { type: resourceToTypeCode(f, slot), type_word: resourceToShapeWord(f, slot),
          resource_family: f, resource_index: slot, color: [75, 145, 220, 255],
          data: i ? [800 + i % 60 * 20, Math.floor(i / 60) * 20, .1, .1, 0, 0, 0] : [0, 0, 3, 3, 0, 0, 0] };
      });
      await loadPayload({shapes});
      if (reference) {
        const source = document.createElement("canvas"); source.width = 6000; source.height = 4000;
        const ctx = source.getContext("2d");
        ctx.fillStyle = "#81939e"; ctx.fillRect(0, 0, 6000, 4000);
        for (let i = 0; i < 100; i++) {
          ctx.fillStyle = `hsl(${i * 13 % 360} 40% 65%)`;
          ctx.fillRect(i * 59, i * 37, 130, 80);
        }
        await loadOverlayImageFromUrl(source.toDataURL("image/png"), "24MP-test-reference.png");
        source.width = source.height = 1;
      }
      const object = vinylObjects()[0];
      canvas.setViewportTransform([1, 0, 0, 1, canvas.width / 2, canvas.height / 2]);
      selectObjects([object], "curve benchmark");
      await Promise.all([...selectionOutlinePathPromises.values()]);
      canvas.renderAll();
      return { family: object.kloudy.resource_family, index: object.kloudy.resource_index,
        count, pathCommands: object.path?.length, outlineCommands: selectedShapeOutlineHelpers.get(object)?.path?.length };
    }, {family, index, count, reference});
    await page.waitForTimeout(1200);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: throttle });
    await cdp.send("Profiler.enable");
    await cdp.send("Profiler.start");
    await page.evaluate(() => { window.curveMetrics = { functions: {}, cache: {}, frames: [], tasks: [] }; });
    for (let repeat = 0; repeat < 3; repeat++) {
      const points = await page.evaluate(() => {
        const o = vinylObjects()[0]; o.setCoords();
        const b = canvas.upperCanvasEl.getBoundingClientRect(), p = o.oCoords.mtr;
        const center = fabric.util.transformPoint(o.getCenterPoint(), canvas.viewportTransform);
        return { x: p.x + b.left, y: p.y + b.top, cx: center.x + b.left, cy: center.y + b.top };
      });
      await page.mouse.move(points.x, points.y);
      await page.mouse.down();
      const dx = points.x - points.cx, dy = points.y - points.cy;
      for (let i = 1; i <= 14; i++) {
        const a = i / 14 * .75;
        await page.mouse.move(points.cx + dx * Math.cos(a) - dy * Math.sin(a), points.cy + dx * Math.sin(a) + dy * Math.cos(a));
      }
      await page.mouse.up();
      await page.mouse.move(points.cx, points.cy);
      await page.mouse.down();
      await page.mouse.move(points.cx + 18, points.cy + 12, { steps: 12 });
      await page.mouse.move(points.cx, points.cy, { steps: 12 });
      await page.mouse.up();
      await page.mouse.move(points.cx, points.cy);
      for (const delta of [-450, -450, 450, 450]) {
        await page.mouse.wheel(0, delta);
        await page.waitForTimeout(100);
      }
      await page.waitForTimeout(380);
    }
    const metrics = await page.evaluate(() => {
      const result = curveMetrics; window.curveMetrics = null;
      const sorted = result.frames.slice(1).sort((a, b) => a - b);
      result.frameP95 = sorted[Math.floor(sorted.length * .95)];
      result.frameMax = Math.max(...sorted);
      delete result.frames;
      result.angle = vinylObjects()[0].angle;
      return result;
    });
    if (Math.abs(metrics.angle) < 1) throw new Error("Real rotation did not change shape angle");
    const { profile } = await cdp.send("Profiler.stop");
    const nodes = new Map(profile.nodes.map(n => [n.id, n]));
    const counts = new Map();
    for (let i = 0; i < (profile.samples || []).length; i++) {
      const frame = nodes.get(profile.samples[i]).callFrame;
      const name = `${frame.functionName || "anonymous"} ${frame.url.split("/").pop()}:${frame.lineNumber + 1}`;
      counts.set(name, (counts.get(name) || 0) + (profile.timeDeltas[i] || 0) / 1000);
    }
    const profileTop = [...counts].sort((a, b) => b[1] - a[1]).slice(0, 20);
    results.push({ ...fixture, throttle, reference, metrics, profileTop });
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  }
  await cdp.detach();
  return results;
}
