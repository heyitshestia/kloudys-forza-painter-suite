async page => {
  const results = await page.evaluate(async () => {
    const rows = [];
    for (const count of [0, 1, 3]) {
      if (count) await loadPayload({ shapes: Array.from({ length: count }, (_, i) => ({
        type: [1048706, 1048677, 1048678][i], color: [[230, 85, 50, 255], [70, 180, 240, 150], [120, 60, 190, 255]][i],
        data: [-130 + i * 130, 0, .75, .75, i * 17, 0, 0],
      })) });
      else if (vinylObjects().length) throw Error('Empty-reference case requires a fresh canvas');
      const source = document.createElement('canvas'); source.width = 4096; source.height = 2048;
      const ctx = source.getContext('2d');
      for (const [x, y, color] of [[0, 0, '#aabbee'], [2048, 0, '#33bb88'], [0, 1024, '#eeaa44'], [2048, 1024, 'rgba(170,70,180,.5)']]) {
        ctx.fillStyle = color; ctx.fillRect(x, y, 2048, 1024);
      }
      await editorReference.loadOverlayImageFromUrl(source.toDataURL(), 'large-preview-quadrants.png');
      source.width = source.height = 1;
      editorReference.image.set({ left: 0, top: 0, scaleX: .18, scaleY: .18, opacity: .55 });
      editorReference.image.setCoords();
      for (const mode of ['below', 'above']) for (const zoom of [.8, 1.3]) {
        setOverlayLayerMode(mode, { persist: false });
        canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2, canvas.height / 2]);
        canvas.discardActiveObject(); editorRenderer.endHybridRenderNow(); canvas.renderAll();
        const before = JSON.stringify(snapshotShapes());
        if (!editorRenderer.hybridRenderNow()) throw Error('Large-reference preview rejected: ' + editorRenderer.disabledReason);
        const { gl, element } = editorRenderer.renderer;
        let compared = 0, maxDifference = 0;
        for (let y = -140; y <= 140; y += 35) for (let x = -320; x <= 320; x += 40) {
          const p = fabric.util.transformPoint(new fabric.Point(x + .31, y + .37), canvas.viewportTransform);
          const sx = Math.round(p.x), sy = Math.round(p.y);
          if (sx < 2 || sy < 2 || sx >= canvas.width - 2 || sy >= canvas.height - 2) continue;
          const neighborhood = canvas.contextContainer.getImageData(sx - 1, sy - 1, 3, 3).data;
          const expected = Array.from(neighborhood.slice(16, 20));
          // Exclude anti-aliased boundaries; compare solid and alpha-blended interiors.
          if (Array.from({ length: 9 }, (_, i) => i).some(i => expected.some((v, c) => Math.abs(v - neighborhood[i * 4 + c]) > 2))) continue;
          const actual = new Uint8Array(4);
          gl.readPixels(sx, element.height - 1 - sy, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, actual);
          const difference = Math.max(...expected.map((v, i) => Math.abs(v - actual[i])));
          maxDifference = Math.max(maxDifference, difference); compared++;
        }
        if (compared < 80 || maxDifference > 4) throw Error(`Preview pixel mismatch ${JSON.stringify({count,mode,zoom,compared,maxDifference})}`);
        if (JSON.stringify(snapshotShapes()) !== before) throw Error('Preview changed shape data');
        rows.push({count,mode,zoom,compared,maxDifference});
      }
      await flushPendingAutosave();
      const recovered = await readAutosavePayload();
      if (JSON.stringify(recovered.shapes) !== JSON.stringify(snapshotShapes())) throw Error('Preview changed recovered data');
    }
    editorRenderer.endHybridRenderNow();
    canvas.renderAll();
    return rows;
  });
  await page.screenshot({path:path.join(output,'large-reference-pixels.png')});
  return {cases:results,exactRecovery:true};
}
