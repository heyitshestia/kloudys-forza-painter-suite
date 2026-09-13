async page => {
  const results = [];
  const families = await page.evaluate(() => FAMILY_ORDER.slice());
  for (const family of families) {
    results.push(await page.evaluate(async family => {
      const shapes = Array.from({ length: 40 }, (_, i) => ({
        type: editorCatalog.resourceToTypeCode(family, i + 1), type_word: editorCatalog.resourceToShapeWord(family, i + 1),
        resource_family: family, resource_index: i + 1,
        color: [70 + i * 13 % 170, 60 + i * 37 % 170, 80 + i * 17 % 160, i % 3 ? 255 : 137],
        data: [(i % 10) * 140 - 630, Math.floor(i / 10) * 140 - 210, .8, .8, (i % 6) * 27, i % 5 ? 0 : .1, 0],
      }));
      await loadPayload({ shapes });
      const objects = vinylObjects();
      const pathBefore = JSON.stringify(objects.map(o => o.path));
      const comparisons = [];
      for (const zoom of [.04, .6, 2, 8]) {
        canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2, canvas.height / 2]);
        objects.forEach((o, i) => o.set({ flipX: i % 4 === 0, flipY: i % 7 === 0 }));
        selectObjects(objects.slice(0, 2), "native fill selection regression");
        const exportBefore = JSON.stringify(objects.map(o => objectToShape(o, { includeEditorMeta: true })));
        const hooked = [...new Set([...objects, ...canvas.getObjects(), ...objects.map(o => o.clipPath)].filter(o => o?._renderPathCommands === renderNativeTriangleFill))];
        const pixels = [], times = [];
        for (const baseline of [true, false]) {
          hooked.forEach(o => { o._renderPathCommands = baseline ? fabric.Path.prototype._renderPathCommands : renderNativeTriangleFill; o.dirty = true; });
          const t = performance.now(); canvas.renderAll(); times.push(performance.now() - t);
          pixels.push(canvas.contextContainer.getImageData(0, 0, canvas.width, canvas.height).data);
        }
        let changes = 0;
        for (let i = 0; i < pixels[0].length; i++) if (pixels[0][i] !== pixels[1][i]) changes++;
        if (changes || exportBefore !== JSON.stringify(objects.map(o => objectToShape(o, { includeEditorMeta: true })))) {
          throw new Error(`${family} zoom ${zoom}: ${changes} changed channels or changed export`);
        }
        comparisons.push({ zoom, optimizedObjects: hooked.length, changedChannels: changes, baselineMs: times[0], patchedMs: times[1] });
        canvas.discardActiveObject();
      }
      if (pathBefore !== JSON.stringify(objects.map(o => o.path))) throw new Error(`${family}: native path geometry mutated`);
      // Mask cutouts use the fill hook; stroked outlines must use Fabric's closed paths.
      const owner = objects.find(o => o._renderPathCommands === renderNativeTriangleFill);
      if (owner) {
        for (const helper of [makeMaskCutoutForObject(owner), makeMaskOutlineForObject(owner)]) {
          const element = document.createElement("canvas"); element.width = element.height = 256;
          const ctx = element.getContext("2d");
          const draws = [];
          for (const baseline of [true, false]) {
            ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, 256, 256);
            ctx.fillStyle = "#abcdef"; ctx.fillRect(0, 0, 256, 256);
            ctx.translate(128, 128); ctx.scale(.5, .5);
            helper._renderPathCommands = baseline ? fabric.Path.prototype._renderPathCommands : renderNativeTriangleFill;
            helper._render(ctx);
            draws.push(ctx.getImageData(0, 0, 256, 256).data);
          }
          if (draws[0].some((v, i) => v !== draws[1][i])) throw new Error(`${family}: mask helper pixels changed`);
          discardFabricObject(helper);
          element.width = element.height = 1;
        }
      }
      return { family, slots: 40, comparisons, exportAndGeometryExact: true };
    }, family));
  }
  await page.screenshot({ path: "native-fill-final.png" });
  return { slots: results.length * 40, families: results };
}
