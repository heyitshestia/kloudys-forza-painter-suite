async page => {
  return await page.evaluate(async () => {
    let cases = 0, samples = 0;
    const source = document.createElement("canvas"); source.width = source.height = 384;
    const context = source.getContext("2d", { willReadFrequently: true });
    const families = ["Primitives", "Gradient_Shapes", "Community_Vinyls_1", "Community_Vinyls_2", "Community_Vinyls_3", "Community_Vinyls_4", "Tears", "Paint_Splats"];
    for (const family of families) {
      const shapes = Array.from({length: 40}, (_, i) => ({type: resourceToTypeCode(family, i + 1), color: [60, 130, 210, i % 5 ? 255 : 91], data: [0, 0, 1, 1, 0, 0, 0]}));
      await loadPayload({ shapes });
      for (const object of vinylObjects()) {
        const original = JSON.stringify(objectToShape(object));
        for (const zoom of [.25, 1, 4]) {
          object.set({ angle: 37, flipX: zoom === 4, skewX: zoom === .25 ? 12 : 0 });
          canvas.setViewportTransform([zoom, 0, 0, zoom, 192, 192]);
          const caching = object.objectCaching;
          object.objectCaching = false;
          context.clearRect(0, 0, 384, 384); context.save(); context.transform(...canvas.viewportTransform); object.render(context); context.restore();
          object.objectCaching = caching;
          const before = JSON.stringify(objectToShape(object));
          for (const tolerance of [0, 4]) {
            canvas.targetFindTolerance = tolerance;
            for (const [x, y] of [[100, 100], [160, 160], [192, 192], [210, 140], [270, 250], [320, 320]]) {
              const radius = tolerance, size = radius * 2 || 1;
              const pixels = context.getImageData(x - radius, y - radius, size, size).data;
              let visible = false;
              for (let i = 3; i < pixels.length; i += 4) if (pixels[i]) visible = true;
              const actual = !canvas.isTargetTransparent(object, x, y);
              if (actual !== visible) throw new Error(`${family}/${object.kloudy.resource_index} zoom ${zoom}, ${x},${y} radius ${radius}: actual ${actual}, expected ${visible}, alpha ${Math.max(...pixels.filter((_, i) => i % 4 === 3))}, image ${object.type}`);
              samples++;
            }
          }
          if (object.objectCaching !== caching || JSON.stringify(objectToShape(object)) !== before) throw new Error("Picking mutated artwork or caching");
          cases++;
        }
        object.set({angle: 0, flipX: false, skewX: 0});
        if (JSON.stringify(objectToShape(object)) !== original) throw new Error("Fixture did not restore geometry");
      }
    }
    canvas.targetFindTolerance = VINYL_HIT_TOLERANCE;
    const object = vinylObjects()[0], render = object.render;
    const caching = object.objectCaching, background = object.selectionBackgroundColor;
    object.render = () => { throw new Error("Injected picking render failure"); };
    let threw = false;
    try { canvas.isTargetTransparent(object, 192, 192); }
    catch (error) { threw = error.message === "Injected picking render failure"; }
    finally { object.render = render; }
    const transform = canvas.contextCache.getTransform();
    if (!threw || object.objectCaching !== caching || object.selectionBackgroundColor !== background
      || transform.a !== 1 || transform.d !== 1 || transform.e !== 0 || transform.f !== 0) throw new Error("Picking failure leaked render state");
    if (!canvas.contextCache.getContextAttributes().willReadFrequently) throw new Error("Picking surface is not CPU-backed");
    const expected = JSON.stringify(vinylObjects().map(o => objectToShape(o)));
    canvas.setDimensions({width: 720, height: 500});
    if (canvas.cacheCanvasEl.width !== canvas.width || canvas.cacheCanvasEl.height !== canvas.height) throw new Error("Picking surface did not resize with the editor");
    if (expected !== JSON.stringify(vinylObjects().map(o => objectToShape(o)))) throw new Error("Resizing picking surface changed export");
    source.width = source.height = 1;
    return { shapes: families.length * 40, transformCases: cases, alphaSamples: samples, failureCleanup: true, resize: true };
  });
}
