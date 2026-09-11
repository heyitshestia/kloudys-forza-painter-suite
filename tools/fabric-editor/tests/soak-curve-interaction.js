async page => {
  await page.setViewportSize({width: 1600, height: 1000});
  const cdp = await page.context().newCDPSession(page);
  await page.evaluate(async () => {
    await loadPayload({shapes: Array.from({length: 3000}, (_, i) => ({
      type: i === 2999 ? 1048706 : 1048677,
      color: [i % 200 + 40, 110, 170, 255],
      data: i === 2999 ? [0, 0, 2, 2, 0, 0, 0] : [i % 60 * 24 - 720, Math.floor(i / 60) * 24 - 600, .12, .12, 0, 0, 0],
    }))});
    const source = document.createElement("canvas"); source.width = 6000; source.height = 4000;
    const ctx = source.getContext("2d"); ctx.fillStyle = "#829ba0"; ctx.fillRect(0, 0, 6000, 4000);
    for (let i = 0; i < 90; i++) { ctx.fillStyle = `hsl(${i * 13 % 360} 45% 60%)`; ctx.fillRect(i * 65, i * 43, 320, 140); }
    await loadOverlayImageFromUrl(source.toDataURL(), "soak-24MP-reference.png");
    source.width = source.height = 1;
    canvas.setViewportTransform([1, 0, 0, 1, canvas.width / 2, canvas.height / 2]);
    selectObjects([vinylObjects().at(-1)], "soak");
    await Promise.all([...selectionOutlinePathPromises.values()]);
    await flushPendingAutosave();
    window.curveSoak = { frames: [], tasks: [] };
    let last = performance.now();
    function frame(now) { if (curveSoak.frames.length < 10000) curveSoak.frames.push(now - last); last = now; requestAnimationFrame(frame); }
    requestAnimationFrame(frame);
    new PerformanceObserver(list => curveSoak.tasks.push(...list.getEntries().map(e => e.duration))).observe({entryTypes:["longtask"]});
  });
  const started = Date.now(), rows = [];
  let cycles = 0, minute = 0;
  const geometry = () => page.evaluate(() => {
    const o = vinylObjects().at(-1); o.setCoords();
    const rect = canvas.upperCanvasEl.getBoundingClientRect();
    const world = fabric.util.transformPoint(o.getCenterPoint(), canvas.viewportTransform);
    const p = point => ({x: point.x + rect.left, y: point.y + rect.top});
    return {center: p(world), rotate: p(o.oCoords.mtr), right: p(o.oCoords.mr),
      origin:p(new fabric.Point(canvas.viewportTransform[4],canvas.viewportTransform[5])),
      angle:o.angle, scaleX:o.scaleX, width:o.width, zoom:canvas.getZoom()};
  });
  const drag = async (a, b, steps = 5) => {
    await page.mouse.move(a.x, a.y); await page.mouse.down();
    await page.mouse.move(b.x, b.y, {steps}); await page.mouse.up();
  };
  while (Date.now() - started < 21 * 60000) {
    let p = await geometry();
    const angle = ((cycles % 2 ? 0 : 20) - p.angle) * Math.PI / 180;
    const rx = p.rotate.x-p.center.x, ry = p.rotate.y-p.center.y;
    await drag(p.rotate, {x:p.center.x+rx*Math.cos(angle)-ry*Math.sin(angle), y:p.center.y+rx*Math.sin(angle)+ry*Math.cos(angle)});
    p = await geometry();
    await drag(p.center, {x:p.origin.x + (cycles % 2 ? -6 : 6), y:p.origin.y});
    p = await geometry();
    const resize = ((cycles % 2 ? 2 : 2.05) - p.scaleX) * p.width * p.zoom;
    const radians = p.angle * Math.PI / 180;
    await drag(p.right, {x:p.right.x + resize * Math.cos(radians), y:p.right.y + resize * Math.sin(radians)});
    p = await geometry();
    await page.mouse.move(p.center.x, p.center.y);
    await page.mouse.wheel(0, -120); await page.waitForTimeout(50);
    await page.mouse.wheel(0, 120); await page.waitForTimeout(100);
    cycles++;
    if (Date.now() - started >= minute * 60000) {
      await cdp.send("HeapProfiler.collectGarbage");
      const heap = await cdp.send("Runtime.getHeapUsage");
      const row = await page.evaluate(() => {
        const frames = curveSoak.frames.splice(0).sort((a,b)=>a-b), tasks = curveSoak.tasks.splice(0);
        const object = vinylObjects().at(-1);
        if (vinylObjects().length !== 3000 || !object.calcOwnMatrix().every(Number.isFinite)) throw new Error("Soak corrupted layers or transform");
        return {frames:frames.length, frameP95:frames[Math.floor(frames.length*.95)], frameMax:Math.max(...frames),
          longTasks:tasks.length, longestTask:Math.max(0,...tasks), history:history.length,
          objects:canvas.getObjects().length, outlines:selectedShapeOutlineHelpers.size,
          recovering:autosaveStatus, angle:object.angle, scale:object.scaleX};
      });
      rows.push({minute, elapsedMs:Date.now()-started, cycles, heap, ...row});
      console.log(JSON.stringify({soakMinute:rows.at(-1)}));
      fs.writeFileSync(path.join(output, "soak-progress.json"), JSON.stringify(rows, null, 2));
      minute++;
    }
  }
  const recovery = await page.evaluate(async () => {
    await flushPendingAutosave();
    if (!autosaveStatus.serverOk || !autosaveStatus.browserOk) throw new Error("Final recovery checkpoint not acknowledged");
    return {...autosaveStatus};
  });
  await cdp.detach();
  return {durationMs:Date.now()-started, cycles, rows, recovery};
}
