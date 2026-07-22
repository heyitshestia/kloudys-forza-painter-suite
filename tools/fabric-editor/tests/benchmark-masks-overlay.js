async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const layerCount = 3000;
    const shapes = Array.from({ length: layerCount }, (_value, index) => {
      const mask = index > 0 && index % 97 === 0;
      const pairIndex = mask ? index - 1 : index;
      return {
        type: 1048677,
        type_word: 101,
        resource_family: "Primitives",
        resource_index: 1,
        color: mask ? [255, 255, 255, 220] : [40 + index % 180, 100 + index % 120, 190, 230],
        data: [
          -780 + (pairIndex % 50) * 32,
          470 - Math.floor(pairIndex / 50) * 16,
          mask ? 0.12 : 0.2,
          mask ? 0.12 : 0.2,
          0,
          0,
          mask ? 1 : 0,
        ],
        mask,
      };
    });
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    clearAutosave();
    await loadPayload({ shapes });

    const source = document.createElement("canvas");
    source.width = 96;
    source.height = 96;
    const context = source.getContext("2d");
    context.fillStyle = "rgba(255,30,90,0.75)";
    context.fillRect(0, 0, 96, 96);
    context.fillStyle = "rgba(40,220,255,0.95)";
    context.fillRect(16, 16, 64, 64);
    overlayImage = new fabric.Image(source, {
      originX: "center",
      originY: "center",
      left: 0,
      top: 0,
      scaleX: 6,
      scaleY: 6,
      opacity: 0.6,
      selectable: false,
      evented: false,
      excludeFromExport: true,
    });
    overlayImage.kloudyOverlay = true;
    canvas.add(overlayImage);
    overlayLayerMode = "above";

    const samples = [];
    for (let index = 0; index < 30; index += 1) {
      const start = performance.now();
      if (!hybridRenderNow()) throw new Error("Hybrid renderer did not run with masks and an overlay.");
      samples.push(performance.now() - start);
    }
    const gl = hybridRenderer.gl;
    const pixels = new Uint8Array(hybridRenderer.element.width * hybridRenderer.element.height * 4);
    gl.readPixels(0, 0, hybridRenderer.element.width, hybridRenderer.element.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    let visiblePixels = 0;
    for (let index = 3; index < pixels.length; index += 4) {
      if (pixels[index] > 0) visiblePixels += 1;
    }
    const error = gl.getError();
    canvas.remove(overlayImage);
    overlayImage = null;
    return {
      layers: vinylObjects().length,
      masks: vinylObjects().filter((object) => object.kloudy.mask).length,
      hybridAllowed: hybridShouldUse(vinylObjects()),
      averageMs: samples.reduce((total, value) => total + value, 0) / samples.length,
      p95Ms: samples.slice().sort((a, b) => a - b)[Math.floor(samples.length * 0.95)],
      visiblePixels,
      webglError: error,
    };
  });
}
