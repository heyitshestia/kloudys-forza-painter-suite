async page => {
  const result = await page.evaluate(async () => {
    const families = ['Primitives', 'Tears', 'Racing_Icons', 'Flames', 'Paint_Splats', 'Tribal', 'Nature', 'Upper_Letters_1', 'Gradient_Shapes'];
    const shapes = families.flatMap((family, f) => [1, 12, 30, 39].map((slot, s) => ({
      type: editorCatalog.resourceToTypeCode(family, slot), resource_family: family, resource_index: slot,
      color: [45 + f * 20, 65 + s * 40, 180 - f * 11, s % 2 ? 117 : 255],
      mask: f < 2 && s === 3, editor_id: `pixel-${f}-${s}`,
      data: [(f % 3 - 1) * 200 + s * 27, (Math.floor(f / 3) - 1) * 190 + s * 21,
        s % 2 ? -.47 : .61, .31 + s * .14, f * 23 + s * 11, s % 2 ? .12 : 0, f < 2 && s === 3 ? 1 : 0],
    })));
    await loadPayload({ shapes });
    const source = document.createElement('canvas'); source.width = 1024; source.height = 768;
    const ctx = source.getContext('2d');
    ctx.fillStyle = '#6cb78a'; ctx.fillRect(0, 0, 1024, 768);
    ctx.fillStyle = 'rgba(120,50,190,.47)'; ctx.fillRect(210, 110, 480, 380);
    await editorReference.loadOverlayImageFromUrl(source.toDataURL(), 'cache-reference.png');
    editorReference.image.set({ left: 0, top: 0, scaleX: .7, scaleY: .7, opacity: .55 });
    const coverage = {
      gradientImages: vinylObjects().filter(o => o.kloudy.resource_family === 'Gradient_Shapes' && o.type === 'image').length,
      masks: vinylObjects().filter(o => o.kloudy.mask).length,
      cutouts: canvas.getObjects().filter(o => o.kloudyMaskCutout).length,
      maskOutlines: canvas.getObjects().filter(o => o.kloudyMaskOutline).length,
    };
    if (!coverage.gradientImages || !coverage.masks || !coverage.cutouts || !coverage.maskOutlines) {
      throw Error(`Missing gradient/mask coverage: ${JSON.stringify(coverage)}`);
    }
    const rows = [];
    const pixels = () => canvas.contextContainer.getImageData(0, 0, canvas.lowerCanvasEl.width, canvas.lowerCanvasEl.height).data;
    const compare = (label, requiredFallback) => {
      const objects = canvas.getObjects().filter(o => o.type === 'path');
      if (!objects.length) throw Error(`${label}: missing native path coverage`);
      for (const object of objects) {
        if (object.drawCacheOnCanvas !== fabric.Object.prototype.drawCacheOnCanvas) {
          throw Error(`${label}: native cache draw must retain Fabric sampling`);
        }
      }
      const saved = JSON.stringify(snapshotShapes());
      canvas.renderAll(); const before = pixels();
      const draw = fabric.Object.prototype.drawCacheOnCanvas;
      const calls = { baseline: 0, requiredFallback: 0 };
      objects.forEach(object => { object.drawCacheOnCanvas = function (context) {
        calls.baseline++;
        if (requiredFallback?.(this)) calls.requiredFallback++;
        return draw.call(this, context);
      }; });
      try { canvas.renderAll(); }
      finally { objects.forEach(object => { delete object.drawCacheOnCanvas; }); }
      const after = pixels();
      let changed = 0;
      for (let i = 0; i < before.length; i++) if (before[i] !== after[i]) changed++;
      rows.push({ label, comparedObjects: objects.length, changed, calls });
      if (changed) throw Error(`${label}: ${changed} pixel channels changed`);
      if (requiredFallback && !calls.requiredFallback) throw Error(`${label}: fallback was not exercised`);
      if (saved !== JSON.stringify(snapshotShapes())) throw Error(`${label}: serialization changed`);
    };
    for (const mode of ['above', 'below']) {
      setOverlayLayerMode(mode, { persist: false });
      for (const zoom of [.04, .37, 1.1, 3.25, 8]) {
        canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2 + .31, canvas.height / 2 + .67]);
        selectObjects([], 'cache pixel test'); compare(`${mode}/zoom-${zoom}/none`);
      }
    }
    canvas.setViewportTransform([1.1, 0, 0, 1.1, canvas.width / 2, canvas.height / 2]);
    const objects = vinylObjects();
    selectObjects([objects[0]], 'cache pixel selection');
    if (selectionOutlinePathPromises.size) await Promise.all(selectionOutlinePathPromises.values());
    compare('single-selection');
    selectObjects(objects.filter(o => !o.kloudy.mask).slice(0, 12), 'cache pixel selection');
    const selection = canvas.getActiveObject();
    selection.set({ left: selection.left + 13.25, top: selection.top - 9.75, angle: 17,
      scaleX: 1.17, scaleY: .83, skewX: 11 }); selection.setCoords();
    compare('active-selection-transform');
    canvas.discardActiveObject();
    objects[0].set({ fill: '#226baa', opacity: .42 });
    objects[1].set({ visible: false });
    compare('color-opacity-visibility-invalidated');
    objects[0].set({ shadow: new fabric.Shadow({ color: '#000000', blur: 4, offsetX: 2, offsetY: 3 }) });
    compare('shadow-fallback', o => !!o.shadow);
    objects[0].set({ shadow: null, stroke: '#ff0000', strokeWidth: 2 });
    compare('stroke-fallback', o => o.hasStroke());
    objects[0].set({ stroke: null, strokeWidth: 0, clipPath: new fabric.Circle({ radius: 20, originX: 'center', originY: 'center' }) });
    compare('clip-fallback', o => !!o.clipPath);
    return { rows, exactPixels: true, exactSerialization: true, families, coverage,
      pathCommands: objects.reduce((n, o) => n + (o.path?.length || 0), 0),
      maxPathCommands: Math.max(...objects.map(o => o.path?.length || 0)) };
  });
  fs.writeFileSync(path.join(output, 'cache-pixels.json'), JSON.stringify(result, null, 2));
  return result;
}
