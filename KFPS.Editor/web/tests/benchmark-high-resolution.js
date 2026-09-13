async page => {
  const cdp = await page.context().newCDPSession(page);
  const rows = [];
  try {
    await page.evaluate(async () => {
      await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
        type: i % 8 ? 1048677 : 1048777, color: [40 + i % 180, 90 + i % 120, 210, 255],
        mask: i > 0 && i % 17 === 0,
        data: [i % 60 * 24 - 720, Math.floor(i / 60) * 24 - 600, .18, .18, 0, 0, i > 0 && i % 17 === 0 ? 1 : 0],
      })) });
      await flushPendingAutosave();
    });
    for (const viewport of [{ width: 1440, height: 900, deviceScaleFactor: 1 },
      { width: 3840, height: 2160, deviceScaleFactor: 1 },
      { width: 1920, height: 1080, deviceScaleFactor: 2 }]) {
      await cdp.send("Emulation.setDeviceMetricsOverride", { ...viewport, mobile: false });
      await page.waitForTimeout(500);
      const row = await page.evaluate(async viewport => {
        fitDesignView();
        editorRenderer.endHybridRenderNow();
        canvas.renderAll();
        const pixels = canvas.lowerCanvasEl.getContext("2d").getImageData(0, 0, canvas.lowerCanvasEl.width, canvas.lowerCanvasEl.height).data;
        let visible = 0;
        for (let i = 3; i < pixels.length; i += 64) if (pixels[i] > 0) visible++;
        if (visible < 100) throw new Error("Blank Fabric canvas at " + JSON.stringify(viewport));
        selectObjects(vinylObjects().slice(0, 40), "high resolution test");
        const samples = [];
        for (let index = 0; index < 8; index++) {
          const began = performance.now();
          nudgeSelected(1, 0); flushPendingNudgeHistory();
          await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          samples.push(performance.now() - began);
        }
        if (!editorRenderer.beginHybridRender("high resolution test") || !editorRenderer.hybridRenderNow()) throw new Error("GPU canvas unavailable");
        const gl = editorRenderer.renderer.gl;
        const sample = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
        gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, sample);
        const colors = new Set();
        for (let i = 0; i < sample.length; i += 64) colors.add(`${sample[i]},${sample[i + 1]},${sample[i + 2]},${sample[i + 3]}`);
        if (colors.size < 10) throw new Error("GPU scene is blank or lacks the fixture colors");
        const result = { viewport, actual: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
          fabric: { width: canvas.lowerCanvasEl.width, height: canvas.lowerCanvasEl.height, visibleSamples: visible },
          gpu: { width: gl.drawingBufferWidth, height: gl.drawingBufferHeight, colors: colors.size }, samples };
        editorRenderer.endHybridRenderNow();
        await flushPendingAutosave();
        if (!editorRecovery.status.serverOk || vinylObjects().length !== 3000) throw new Error("High-resolution edit/recovery failed");
        return result;
      }, viewport);
      rows.push(row);
      await page.screenshot({ path: `viewport-${viewport.width}-${viewport.height}-dpr${viewport.deviceScaleFactor}.png` });
    }
    return { rows, caveat: "Actual Qt renderer with CDP viewport/DPR overrides; not a separate physical 4K monitor." };
  } finally {
    await cdp.send("Emulation.clearDeviceMetricsOverride");
    await cdp.detach();
  }
}
