async page => {
  page.setDefaultTimeout(120000);
  await page.setViewportSize({ width: 1440, height: 900 });
  const results = [];
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 300 }, (_, i) => ({
      type: 1048677, color: [120, 160, 200, 255],
      data: [-500 + i % 30 * 35, 250 - Math.floor(i / 30) * 35, .1, .1, 0, 0, 0],
    })) });
    fitDesignView();
  });
  for (const [width, height] of [[6000, 4000], [8192, 4096]]) {
    const source = await page.evaluate(({ width, height }) => {
      const element = document.createElement("canvas");
      element.width = width; element.height = height;
      const ctx = element.getContext("2d");
      for (const [x, y, color] of [[0, 0, "#ff0000"], [1, 0, "#00ff00"], [0, 1, "#0000ff"], [1, 1, "#ffff00"]]) {
        ctx.fillStyle = color;
        ctx.fillRect(x * width / 2, y * height / 2, width / 2, height / 2);
      }
      // A one-pixel marker proves CPU sampling does not use a resized preview.
      ctx.fillStyle = "#123456"; ctx.fillRect(17, 23, 1, 1);
      const data = element.toDataURL("image/png");
      element.width = element.height = 1;
      return data.split(",")[1];
    }, { width, height });
    const name = `reference-${width}-${height}.png`;
    await page.locator("#overlayInput").setInputFiles({ name, mimeType: "image/png", buffer: Buffer.from(source, "base64") });
    await page.waitForFunction(name => editorReference.source?.fileName === name, name);
    const result = await page.evaluate(async ({ width, height }) => {
      const assert = (value, message) => { if (!value) throw new Error(message); };
      assert(editorReference.image.width === width && editorReference.image.height === height, "Reference dimensions changed");
      assert(editorReference.sampler.width === width && editorReference.sampler.height === height && editorReference.sampler.tiles.size === 0, "Sampler changed dimensions or eagerly decoded reference pixels");
      const originalUrl = editorReference.source.dataUrl;
      $("overlayOpacity").value = "100";
      editorReference.updateOverlay();
      setOverlayLayerMode("above");
      editorReference.image.set({ opacity: 1, angle: 13, flipX: true, skewX: 4 });
      editorReference.image.setCoords();
      markOverlayChanged("large reference transform");
      const sample = (x, y) => {
        const world = fabric.util.transformPoint(new fabric.Point(x - width / 2, y - height / 2), editorReference.image.calcTransformMatrix());
        return editorReference.overlayColorAtCanvasPoint(world.x, world.y);
      };
      assert(JSON.stringify(sample(17, 23)) === "[18,52,86,255]", "Transformed full-resolution pixel sampling changed");
      const gl = editorRenderer.renderer.gl;
      const originalGet = gl.getParameter;
      const originalUpload = gl.texImage2D;
      let uploadedSize = null, temporary = null;
      try {
        editorRenderer.releaseHybridOverlay();
        gl.getParameter = function (key) { return key === this.MAX_TEXTURE_SIZE ? 2048 : originalGet.call(this, key); };
        gl.texImage2D = function (...args) {
          temporary = args[5];
          uploadedSize = [temporary.width, temporary.height];
          return originalUpload.apply(this, args);
        };
        assert(editorRenderer.hybridRenderNow(), "Large reference GPU render did not run");
        assert(uploadedSize[0] === 2048 && uploadedSize[1] === Math.floor(height * 2048 / width), "Preview ignored device texture limit");
        assert(temporary.width === 1 && temporary.height === 1, "Temporary upload canvas retains pixels");
        assert(gl.getError() === 0, "Large reference caused a GPU error");
        assert(editorReference.source.dataUrl === originalUrl && JSON.stringify(sample(17, 23)) === "[18,52,86,255]", "GPU preview changed original source");
        for (const [x, y, expected] of [[.25, .25, [255, 0, 0]], [.75, .25, [0, 255, 0]], [.25, .75, [0, 0, 255]], [.75, .75, [255, 255, 0]]]) {
          const world = fabric.util.transformPoint(new fabric.Point((x - .5) * width, (y - .5) * height), editorReference.image.calcTransformMatrix());
          const screen = fabric.util.transformPoint(world, canvas.viewportTransform);
          const pixel = new Uint8Array(4);
          gl.readPixels(Math.round(screen.x), gl.drawingBufferHeight - 1 - Math.round(screen.y), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
          assert(expected.every((value, index) => Math.abs(value - pixel[index]) <= 3), `GPU reference pixel mismatch: ${pixel}`);
        }
      } finally { gl.getParameter = originalGet; gl.texImage2D = originalUpload; }
      editorRenderer.releaseHybridOverlay();
      assert(editorRenderer.hybridRenderNow() && gl.getError() === 0, "Real device texture upload failed");
      currentProjectName = `Large Reference ${width}`;
      await saveProject();
      assert(!documentDirty, "Large reference save failed");
      const response = await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(`${currentProjectName}.fabric-project.json`)}`, { cache: "no-store" });
      const saved = await response.json();
      assert(response.ok && saved.payload.editor_source_overlay.data_url === originalUrl, "Saved original reference changed");
      const before = JSON.stringify(editorReference.sourceOverlayProjectState());
      const shapesBefore = JSON.stringify(snapshotShapes());
      await loadProjectPayload(saved.payload, currentProjectName);
      const after = editorReference.sourceOverlayProjectState();
      const brief = state => ({ ...state, data_url: state.data_url?.length });
      assert(JSON.stringify(after) === before, `Project reopen changed reference/transform: ${JSON.stringify({ before: brief(JSON.parse(before)), after: brief(after) })}`);
      assert(JSON.stringify(snapshotShapes()) === shapesBefore, "Reference changed exported artwork");
      editorReference.image.left += 11;
      editorReference.image.setCoords();
      markOverlayChanged("large reference recovery");
      await flushPendingAutosave();
      const recovery = await readAutosavePayload();
      assert(recovery.editor_source_overlay.data_url === originalUrl, "Recovery did not save original reference");
      return { width, height, uploadedSize, savedExact: true, sourceBytes: originalUrl.length, recoveryExact: true,
        expectedRecovery: JSON.stringify(editorReference.sourceOverlayProjectState()) };
    }, { width, height });
    // Simulate a fresh renderer without the deliberate user-navigation guard.
    await page.evaluate(() => { documentDirty = false; });
    await page.reload();
    await page.waitForFunction(() => window.KfpsDesktop?.ready);
    const recovered = await page.evaluate(async expected => {
      document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
      const payload = await readAutosavePayload();
      await recoverAutosavePayload(payload);
      if (JSON.stringify(editorReference.sourceOverlayProjectState()) !== expected) throw new Error("Reload recovery lost large reference");
      const original = editorReference.image;
      let failed = false;
      try { await editorReference.loadOverlayImageFromUrl("data:image/png;base64,broken", "invalid.png"); } catch (_) { failed = true; }
      if (!failed || editorReference.image !== original) throw new Error("Invalid replacement destroyed large reference");
      editorRenderer.beginHybridRender("large reference visual check");
      editorRenderer.hybridRenderNow();
      return { reloadedRecovery: true, invalidPreserved: true };
    }, result.expectedRecovery);
    delete result.expectedRecovery;
    await page.screenshot({ path: `large-reference-${width}.png` });
    results.push({ ...result, ...recovered });
  }
  await page.evaluate(async () => {
    editorRenderer.endHybridRenderNow();
    const old = editorReference.image;
    editorReference.removeOverlay();
    if (editorReference.image || editorReference.sampler || editorRenderer.renderer.overlay.source || editorRenderer.renderer.overlay.texture || old._element) {
      throw new Error("Removed large reference retains an owner");
    }
    await clearAutosave();
    documentDirty = false;
  });
  return results;
}
