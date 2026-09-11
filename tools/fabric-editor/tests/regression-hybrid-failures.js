async page => {
  const results = [];
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({length: 300}, (_, index) => ({
      type: resourceToTypeCode("Primitives", 1), color: [190, 75, 110, 255],
      data: [-500 + index % 30 * 35, 200 - Math.floor(index / 30) * 40, .3, .3, 0, 0, 0],
    })) });
    const source = document.createElement("canvas");
    source.width = 1000; source.height = 700;
    const context = source.getContext("2d");
    context.fillStyle = "#538ea1"; context.fillRect(0, 0, 1000, 700);
    await loadOverlayImageFromUrl(source.toDataURL(), "render-failure-reference.png");
    source.width = source.height = 1;
    overlayLayerMode = "below";
    overlayImage.set({opacity: 1, visible: true});
    canvas.setViewportTransform([.8, 0, 0, .8, canvas.width / 2, canvas.height / 2]);
    canvas.discardActiveObject(); canvas.renderAll();
  });
  for (const failure of ["upload-throws", "upload-gl-error", "missing-reference", "draw-throws", "context-lost-before-event"]) {
    const result = await page.evaluate(async failure => {
      endHybridRenderNow(); hybridDisabledReason = ""; releaseHybridOverlay();
      const gl = hybridRenderer.gl;
      const original = { texImage2D: gl.texImage2D, getError: gl.getError, isContextLost: gl.isContextLost,
        drawHybridOverlay, drawHybridShapePass };
      const before = JSON.stringify(vinylObjects().map(object => objectToShape(object)));
      const reference = JSON.stringify(sourceOverlayProjectState());
      if (failure === "upload-throws") gl.texImage2D = () => { throw new Error("Injected texture failure"); };
      if (failure === "upload-gl-error") gl.getError = () => gl.OUT_OF_MEMORY;
      if (failure === "missing-reference") drawHybridOverlay = () => false;
      if (failure === "draw-throws") drawHybridShapePass = () => { throw new Error("Injected frame failure"); };
      if (failure === "context-lost-before-event") gl.isContextLost = () => true;
      try {
        if (!beginHybridRender("failure regression")) throw new Error("Fixture did not enter GPU preview");
        if (canvas.lowerCanvasEl.style.visibility === "hidden") throw new Error("Normal canvas hidden before first complete preview");
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        if (hybridRenderActive || canvas.lowerCanvasEl.style.visibility === "hidden" || !hybridRenderer.element.hidden) {
          throw new Error(`${failure} left an incomplete preview visible`);
        }
        if (before !== JSON.stringify(vinylObjects().map(object => objectToShape(object))) || reference !== JSON.stringify(sourceOverlayProjectState())) {
          throw new Error("Render fallback changed the project");
        }
        canvas.renderAll();
        const point = fabric.util.transformPoint(vinylObjects()[0].getCenterPoint(), canvas.viewportTransform);
        const pixels = canvas.contextContainer.getImageData(Math.round(point.x), Math.round(point.y), 1, 1).data;
        if (pixels[3] === 0 || pixels[0] < 40) throw new Error("Fallback canvas is blank/black at the artwork");
        const rect = canvas.upperCanvasEl.getBoundingClientRect();
        return { failure, fallback: true, reason: hybridDisabledReason, x: rect.left + point.x, y: rect.top + point.y };
      } finally {
        gl.texImage2D = original.texImage2D; gl.getError = original.getError; gl.isContextLost = original.isContextLost;
        drawHybridOverlay = original.drawHybridOverlay; drawHybridShapePass = original.drawHybridShapePass;
      }
    }, failure);
    await page.mouse.click(result.x, result.y);
    if (!await page.evaluate(() => selectedVinylObjects().length === 1)) throw new Error(`${failure}: artwork cannot be selected after fallback`);
    results.push(result);
  }
  const resumed = await page.evaluate(async () => {
    hybridDisabledReason = "";
    if (!beginHybridRender("successful handoff")) throw new Error("Could not resume preview in test");
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (!hybridRenderActive || hybridRenderer.element.hidden || canvas.lowerCanvasEl.style.visibility !== "hidden") {
      throw new Error("Successful preview handoff failed");
    }
    endHybridRenderNow();
    beginHybridRender("cancel queued frame");
    endHybridRenderNow();
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (hybridRenderActive || !hybridRenderer.element.hidden || canvas.lowerCanvasEl.style.visibility === "hidden") {
      throw new Error("Cancelled preview resurfaced after settling");
    }
    return true;
  });
  return { results, successfulHandoffAndCancellation: resumed };
}
