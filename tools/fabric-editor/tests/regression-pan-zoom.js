async (page) => {
  page.setDefaultTimeout(180000);
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [70 + index % 170, 140, 220, 255],
      data: [-850 + (index % 60) * 28, 620 - Math.floor(index / 60) * 25, 0.2, 0.2, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    await loadPayload({ shapes });
    window.__interactionStart = {
      zoom: canvas.getZoom(),
      viewport: canvas.viewportTransform.slice(),
    };
  });

  const stage = await page.locator(".canvasStage").boundingBox();
  if (!stage) throw new Error("Canvas stage was not available.");
  const x = stage.x + stage.width * 0.55;
  const y = stage.y + stage.height * 0.52;

  await page.mouse.move(x, y);
  await page.mouse.wheel(0, -240);
  const zoomState = await page.evaluate(() => ({
    zoom: canvas.getZoom(),
    hybridActive: hybridRenderActive,
    hybridVisible: !hybridRenderer.element.hidden,
  }));

  await page.mouse.move(x, y);
  await page.mouse.down({ button: "right" });
  await page.mouse.move(x + 80, y + 45, { steps: 8 });
  await page.mouse.up({ button: "right" });
  const panState = await page.evaluate(() => ({
    viewport: canvas.viewportTransform.slice(),
    hybridActive: hybridRenderActive,
    fabricVisible: canvas.lowerCanvasEl.style.visibility !== "hidden",
  }));

  await page.waitForTimeout(350);
  const settled = await page.evaluate(() => ({
    hybridActive: hybridRenderActive,
    hybridHidden: hybridRenderer.element.hidden,
    fabricVisible: canvas.lowerCanvasEl.style.visibility !== "hidden",
    layers: vinylObjects().length,
  }));
  const start = await page.evaluate(() => window.__interactionStart);
  const panChanged = panState.viewport[4] !== start.viewport[4] || panState.viewport[5] !== start.viewport[5];

  if (zoomState.zoom === start.zoom || !zoomState.hybridActive || !zoomState.hybridVisible) {
    throw new Error("Wheel zoom did not enter the 3000-layer GPU interaction path.");
  }
  if (!panChanged || !panState.hybridActive) throw new Error("Right-drag pan did not use the GPU interaction path.");
  if (settled.hybridActive || !settled.hybridHidden || !settled.fabricVisible) {
    throw new Error("Exact Fabric rendering did not resume after interaction settled.");
  }
  if (settled.layers !== 3000) throw new Error("Pan/zoom interaction changed the layer stack.");

  return { start, zoomState, panState, settled };
}
