async page => {
  const result = await page.evaluate(async () => {
    const rows = [], width = 400, height = 160;
    const board = document.createElement('canvas'); board.width = 1200; board.height = 1760;
    const bc = board.getContext('2d'); bc.fillStyle = '#252525'; bc.fillRect(0, 0, board.width, board.height);
    bc.font = '18px sans-serif'; bc.fillStyle = '#fff';
    ['Product path', 'Sampled triangle union', 'Bundled thumbnail'].forEach((s, i) => bc.fillText(s, 10 + i * 400, 25));
    const makeCanvas = () => { const c = document.createElement('canvas'); c.width = width; c.height = height; return c; };
    const count = c => { const p = c.getContext('2d').getImageData(0, 0, width, height).data; let n = 0;
      for (let i = 3; i < p.length; i += 4) if (p[i] > 16) n++; return n; };
    // Different rasterizers disagree at antialiased edges, not across empty interiors.
    // Tolerate one pixel only at reference boundaries, never inside solid artwork.
    const coverage = (actual, expected) => {
      let interior = 0, missing = 0, missingBeyondEdgeTolerance = 0;
      for (let y = 1; y < height - 1; y++) for (let x = 1; x < width - 1; x++) {
        const i = (y * width + x) * 4 + 3;
        if (expected[i] <= 250) continue;
        interior++;
        if (actual[i] >= 128) continue;
        missing++;
        let covered = false, boundary = false;
        for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
          if (actual[((y + dy) * width + x + dx) * 4 + 3] >= 128) covered = true;
          if (expected[((y + dy) * width + x + dx) * 4 + 3] <= 250) boundary = true;
        }
        if (!boundary || !covered) missingBeyondEdgeTolerance++;
      }
      return { interior, missing, missingBeyondEdgeTolerance };
    };
    const solid = new Uint8ClampedArray(width * height * 4);
    for (let y = 40; y < 49; y++) for (let x = 40; x < 49; x++) solid[(y * width + x) * 4 + 3] = 255;
    const hole = solid.slice();
    for (let y = 43; y < 45; y++) for (let x = 43; x < 45; x++) hole[(y * width + x) * 4 + 3] = 0;
    const interiorHoleMissing = coverage(hole, solid).missingBeyondEdgeTolerance;
    for (let slot = 1; slot <= 40; slot++) {
      const type = editorCatalog.resourceToTypeCode('Racing_Icons', slot);
      const resolved = editorCatalog.typeCodeToResource(type);
      const payload = await editorCatalog.loadResourcePayloadForResolved(resolved);
      const original = JSON.stringify(payload);
      const object = await makeFabricObject({ type, data: [0, 0, 1, 1, 0, 0, 0], color: [255, 255, 255, 255] });
      const scale = Math.min(360 / object.width, 130 / object.height);
      const product = makeCanvas(), reference = makeCanvas(), oldWinding = makeCanvas();
      const fc = new fabric.StaticCanvas(product, { width, height, enableRetinaScaling: false, renderOnAddRemove: false });
      object.set({ left: 200, top: 80, scaleX: scale, scaleY: scale }); fc.add(object); fc.renderAll();
      const ctx = reference.getContext('2d'); ctx.fillStyle = '#fff';
      ctx.translate(200, 80); ctx.scale(scale, scale); ctx.translate(-object.pathOffset.x, -object.pathOffset.y);
      // Union occupancy before antialiasing: repeated overlapping triangles must
      // not accumulate edge alpha and manufacture opaque reference pixels.
      const samples = 4, sampleWidth = width * samples, sampleHeight = height * samples;
      const occupancy = new Uint8Array(sampleWidth * sampleHeight);
      const rasterTriangle = points => {
        const screen = points.map(p => [200 + (p.X - object.pathOffset.x) * scale,
          80 + (p.Y - object.pathOffset.y) * scale]);
        const first = Math.max(0, Math.ceil(Math.min(...screen.map(p => p[1])) * samples - .5));
        const last = Math.min(sampleHeight - 1, Math.floor(Math.max(...screen.map(p => p[1])) * samples - .5));
        for (let y = first; y <= last; y++) {
          const py = (y + .5) / samples, intersections = [];
          for (let edge = 0; edge < 3; edge++) {
            const a = screen[edge], b = screen[(edge + 1) % 3];
            if ((a[1] <= py && py < b[1]) || (b[1] <= py && py < a[1]))
              intersections.push(a[0] + (py - a[1]) * (b[0] - a[0]) / (b[1] - a[1]));
          }
          if (intersections.length !== 2) continue;
          const left = Math.max(0, Math.ceil(Math.min(...intersections) * samples - .5));
          const right = Math.min(sampleWidth - 1, Math.floor(Math.max(...intersections) * samples - .5));
          if (left <= right) occupancy.fill(1, y * sampleWidth + left, y * sampleWidth + right + 1);
        }
      };
      const old = oldWinding.getContext('2d'); old.fillStyle = '#fff';
      old.translate(200, 80); old.scale(scale, scale); old.translate(-object.pathOffset.x, -object.pathOffset.y);
      old.beginPath();
      const alphas = decodeVertexAlphas(payload, payload.Vertices.length);
      for (let i = 0; i < payload.Indices.length; i += 3) {
        const ids = payload.Indices.slice(i, i + 3); if (ids.every(j => alphas[j] === 0)) continue;
        const points = ids.map(j => payload.Vertices[j]);
        rasterTriangle(points);
        ctx.beginPath(); ctx.moveTo(points[0].X, points[0].Y);
        ctx.lineTo(points[1].X, points[1].Y); ctx.lineTo(points[2].X, points[2].Y); ctx.closePath(); ctx.fill();
        old.moveTo(points[0].X, points[0].Y); old.lineTo(points[1].X, points[1].Y);
        old.lineTo(points[2].X, points[2].Y); old.closePath();
      }
      old.fill();
      const overdraw = ctx.getImageData(0, 0, width, height).data;
      const union = ctx.createImageData(width, height);
      let overdrawFalseOpaque = 0;
      for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
        let occupied = 0;
        for (let sy = 0; sy < samples; sy++) for (let sx = 0; sx < samples; sx++)
          occupied += occupancy[(y * samples + sy) * sampleWidth + x * samples + sx];
        const offset = (y * width + x) * 4;
        union.data.set([255, 255, 255, Math.round(255 * occupied / (samples * samples))], offset);
        if (overdraw[offset + 3] > 250 && union.data[offset + 3] < 128) overdrawFalseOpaque++;
      }
      ctx.putImageData(union, 0, 0);
      const pp = product.getContext('2d').getImageData(0, 0, width, height).data;
      const rp = reference.getContext('2d').getImageData(0, 0, width, height).data;
      const measured = coverage(pp, rp);
      const oldMeasured = coverage(old.getImageData(0, 0, width, height).data, rp);
      const blankMeasured = coverage(new Uint8ClampedArray(rp.length), rp);
      rows.push({ slot, product: count(product), reference: count(reference), ...measured, overdrawFalseOpaque,
        oldWindingMissing: oldMeasured.missingBeyondEdgeTolerance,
        blankMissing: blankMeasured.missingBeyondEdgeTolerance,
        resourceUnchanged: JSON.stringify(payload) === original });
      if (slot <= 10) {
        const y = 45 + (slot - 1) * 170; bc.fillStyle = '#fff'; bc.fillText(`Slot ${slot}`, 10, y);
        bc.drawImage(product, 0, y); bc.drawImage(reference, 400, y);
        const img = new Image(); img.src = await editorCatalog.resolveVinylResourceUrl('Racing_Icons', slot, '.png'); await img.decode();
        const s = Math.min(360 / img.width, 130 / img.height);
        bc.drawImage(img, 1000 - img.width * s / 2, y + 80 - img.height * s / 2, img.width * s, img.height * s);
      }
      await fc.dispose();
    }
    const alphaPayload = { Vertices: [{X:0,Y:0},{X:100,Y:0},{X:0,Y:100},{X:100,Y:100}],
      Indices: [0,1,2,0,2,1,1,3,2], VerticesAlpha: [255,255,255,100] };
    const rendered = renderAlphaMeshImagePayload(alphaPayload).element;
    const pixel = rendered.getContext('2d').getImageData(20, 20, 1, 1).data[3];
    return { rows, alphaOpaqueCoverage: pixel, edgeTolerancePixels: 1, interiorHoleMissing, board: board.toDataURL(),
      passed: pixel === 255 && interiorHoleMissing === 4 && rows.every(row => row.product > 0 && row.interior > 0
        && row.missingBeyondEdgeTolerance === 0 && row.blankMissing > 0 && row.resourceUnchanged)
        && rows.slice(0, 4).every(row => row.oldWindingMissing > 0) };
  });
  fs.writeFileSync(path.join(output, 'racing-comparison.png'), Buffer.from(result.board.split(',')[1], 'base64'));
  delete result.board;
  fs.writeFileSync(path.join(output, 'racing-winding.json'), JSON.stringify(result, null, 2));
  return result;
}
