async page => {
  const result = await page.evaluate(async () => {
    await loadPayload({ shapes: [{ type: editorCatalog.resourceToTypeCode('Community_Vinyls_4', 9),
      color: [50, 130, 210, 151], data: [0, 0, 1, 1, 0, 0, 0] }] });
    const object = vinylObjects()[0];
    const geometry = JSON.stringify(object.path), before = JSON.stringify(objectToShape(object));
    const surface = document.createElement('canvas'); surface.width = surface.height = 512;
    const context = surface.getContext('2d', { willReadFrequently: true });
    const guides = [], picking = [];
    const helper = makeMaskOutlineForObject(object);
    const render = helper._render, commands = helper._renderPathCommands;
    for (const [scale, zoom, angle, skew, flipX, flipY] of [
      [.4, 1, 37, 14, true, false], [.8, 1, -75, -22, false, true], [.4, 8, 31, 12, true, true],
    ]) {
      helper.set({ scaleX: scale, scaleY: scale * .8, angle, skewX: skew, flipX, flipY });
      const draws = [];
      for (const baseline of [true, false]) {
        context.setTransform(1, 0, 0, 1, 0, 0); context.clearRect(0, 0, 512, 512);
        context.fillStyle = '#abcdef'; context.fillRect(0, 0, 512, 512);
        context.translate(256, 256); context.scale(zoom, zoom); context.transform(...helper.calcOwnMatrix());
        helper._render = baseline ? fabric.Path.prototype._render : render;
        helper._renderPathCommands = baseline ? fabric.Path.prototype._renderPathCommands : commands;
        helper._render(context);
        draws.push(context.getImageData(0, 0, 512, 512).data);
      }
      let changed = 0, maxDelta = 0, absoluteError = 0, edgeOnly = true;
      for (let i = 0; i < draws[0].length; i++) if (draws[0][i] !== draws[1][i]) {
        changed++; maxDelta = Math.max(maxDelta, Math.abs(draws[0][i] - draws[1][i]));
        absoluteError += Math.abs(draws[0][i] - draws[1][i]);
        const pixel = i - i % 4;
        // A difference must touch an antialiased stroke edge in the baseline,
        // not a uniform interior/exterior region (including newly shifted edges).
        const x = (pixel / 4) % 512, y = Math.floor(pixel / 4 / 512);
        const edge = [[-1, 0], [1, 0], [0, -1], [0, 1]].some(([dx, dy]) => {
          if (x + dx < 0 || x + dx >= 512 || y + dy < 0 || y + dy >= 512) return false;
          const neighbor = ((y + dy) * 512 + x + dx) * 4;
          return [0, 1, 2].some(c => draws[0][neighbor + c] !== draws[0][pixel + c]);
        });
        edgeOnly &&= edge;
      }
      guides.push({ scale, zoom, angle, skew, flipX, flipY, changed, maxDelta, edgeOnly,
        changedFraction: changed / draws[0].length, meanAbsoluteError: absoluteError / draws[0].length });
    }
    discardFabricObject(helper);
    for (const zoom of [.25, 1, 4]) {
      object.set({ angle: 37, skewX: 12, flipX: zoom === 4 });
      canvas.setViewportTransform([zoom, 0, 0, zoom, 256, 256]);
      const caching = object.objectCaching;
      object.objectCaching = false;
      context.setTransform(1, 0, 0, 1, 0, 0); context.clearRect(0, 0, 512, 512);
      context.save(); context.transform(...canvas.viewportTransform); object.render(context); context.restore();
      object.objectCaching = caching;
      for (const tolerance of [0, 4]) {
        canvas.targetFindTolerance = tolerance;
        for (const [x, y] of [[80, 80], [200, 200], [256, 256], [290, 240], [330, 310], [420, 420]]) {
          const size = tolerance * 2 || 1;
          const data = context.getImageData(x - tolerance, y - tolerance, size, size).data;
          let visible = false;
          for (let i = 3; i < data.length; i += 4) if (data[i]) visible = true;
          const actual = !canvas.isTargetTransparent(object, x, y);
          if (actual !== visible) throw Error(`Visible-pixel picking changed at zoom ${zoom}, ${x},${y}, tolerance ${tolerance}`);
          picking.push({ zoom, tolerance, x, y, visible });
        }
      }
      if (object.objectCaching !== caching) throw Error('Picking changed cache policy');
    }
    canvas.targetFindTolerance = VINYL_HIT_TOLERANCE;
    object.set({ angle: 0, skewX: 0, flipX: false });
    if (JSON.stringify(object.path) !== geometry || JSON.stringify(objectToShape(object)) !== before) throw Error('Edge tests changed geometry or export');
    surface.width = surface.height = 1;
    markCurrentHistorySaved('Isolated shape 9 edge checks');
    return { guides, picking, exactGeometry: true, exactExport: true };
  });
  fs.writeFileSync(path.join(output, 'shape9-edges.json'), JSON.stringify(result, null, 2));
  // Zoom increases guide edge coverage. Bound both its affected fraction and
  // intensity, and forbid any interior/exterior changes. Actual artwork and
  // cutouts retain their separate zero-difference gate.
  if (result.guides.some(row => row.changedFraction > .001 || row.meanAbsoluteError > .02 || row.maxDelta > 64 || !row.edgeOnly)) {
    throw Error(`Mask guide edge fidelity exceeded its bound: ${JSON.stringify(result.guides)}`);
  }
  return result;
}
