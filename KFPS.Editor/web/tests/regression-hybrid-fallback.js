async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const shapes = Array.from({ length: 300 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [70 + index % 170, 130, 220, 255],
      data: [-600 + (index % 30) * 40, 300 - Math.floor(index / 30) * 60, 0.25, 0.25, 0, 0, 0],
    }));
    await loadPayload({ shapes });
    const savedInstanced = editorRenderer.renderer.instanced;
    editorRenderer.renderer.instanced = null;
    const rendered = editorRenderer.hybridRenderNow();
    const gl = editorRenderer.renderer.gl;
    const pixels = new Uint8Array(editorRenderer.renderer.element.width * editorRenderer.renderer.element.height * 4);
    gl.readPixels(0, 0, editorRenderer.renderer.element.width, editorRenderer.renderer.element.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    editorRenderer.renderer.instanced = savedInstanced;
    let nonBackgroundPixels = 0;
    const background = editorRenderer.hybridCanvasBackgroundColor(editorRenderer.renderer);
    for (let index = 0; index < pixels.length; index += 4) {
      if (
        Math.abs(pixels[index] - background[0]) > 2
        || Math.abs(pixels[index + 1] - background[1]) > 2
        || Math.abs(pixels[index + 2] - background[2]) > 2
      ) nonBackgroundPixels += 1;
    }
    const result = {
      rendered,
      nonBackgroundPixels,
      webglError: gl.getError(),
      instancingRestored: editorRenderer.renderer.instanced === savedInstanced,
    };
    if (!result.rendered || result.nonBackgroundPixels < 100) throw new Error("Fallback renderer produced a blank frame.");
    if (result.webglError !== 0) throw new Error(`Fallback renderer WebGL error: ${result.webglError}`);
    if (!result.instancingRestored) throw new Error("Instanced renderer was not restored after fallback test.");
    return result;
  });
}
