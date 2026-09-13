async page => {
  const setup = await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, index) => ({
      type: index === 2999 ? 1048706 : 1048677,
      color: [40 + index % 170, 150, 210, 255],
      data: [-700 + index % 60 * 24, 600 - Math.floor(index / 60) * 24, .18, .18, 0, 0, 0],
    })) }, { projectName: null });
    const reference = document.createElement('canvas');
    reference.width = 6000; reference.height = 4000;
    const context = reference.getContext('2d');
    context.fillStyle = '#889f93'; context.fillRect(0, 0, 6000, 4000);
    await editorReference.loadOverlayImageFromUrl(reference.toDataURL(), 'dense-numeric-reference.png');
    reference.width = reference.height = 1;
    selectObjects([vinylObjects().at(-1)], 'dense numeric');
    activateDockPanel('propertiesPane'); fitDesignView();
    await flushPendingAutosave();
    window.numericUntouched = JSON.stringify(snapshotShapes().slice(0, -1));
    window.numericFrames = [];
    window.numericActive = false;
    let last = 0;
    const frame = now => {
      if (numericActive && last) numericFrames.push(now - last);
      last = numericActive ? now : 0;
      window.numericFrameHandle = requestAnimationFrame(frame);
    };
    numericFrameHandle = requestAnimationFrame(frame);
    return { layers: vinylObjects().length, reference: [editorReference.image.width, editorReference.image.height] };
  });
  const rows = [];
  try {
    for (const order of ['below', 'above']) {
      await page.evaluate(order => { setOverlayLayerMode(order); numericFrames = []; numericActive = true; }, order);
      for (let cycle = 0; cycle < 6; cycle++) {
        for (const [id, value] of [
          ['xInput', `12 * ${cycle + 1}`], ['yInput', `8 * ${cycle + 1}`],
          ['sxInput', `.2 + ${cycle} / 100`], ['syInput', `.3 + ${cycle} / 100`],
          ['rotInput', `${cycle + 1} * 15`], ['skewInput', `${cycle + 1} * 2`],
        ]) {
          const input = page.locator(`#${id}`);
          await input.fill(value); await input.press('Enter');
          if (await input.getAttribute('aria-invalid') === 'true') throw Error(`Valid expression rejected: ${id}`);
        }
        await page.locator('#xInput').press('Shift+ArrowUp');
        await page.locator('#yInput').press('Alt+ArrowDown');
      }
      await page.evaluate(() => { document.activeElement?.blur(); });
      // Real label-drag commits once, then a cancelled drag restores exactly.
      const label = page.locator('[data-numeric-for="rotInput"]');
      await label.scrollIntoViewIfNeeded();
      const rect = await label.boundingBox();
      const point = { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
      const before = await page.evaluate(() => objectToShape(vinylObjects().at(-1)));
      await page.mouse.move(point.x, point.y); await page.mouse.down();
      await page.mouse.move(point.x + 32, point.y, { steps: 12 }); await page.mouse.up();
      const dragged = await page.evaluate(() => objectToShape(vinylObjects().at(-1)));
      if (JSON.stringify(before) === JSON.stringify(dragged)) throw Error('Numeric label drag did not edit the shape');
      await page.mouse.move(point.x, point.y); await page.mouse.down();
      await page.mouse.move(point.x - 25, point.y, { steps: 8 });
      await page.keyboard.press('Escape'); await page.mouse.up();
      const row = await page.evaluate(async ({ order, dragged }) => {
        numericActive = false;
        const current = objectToShape(vinylObjects().at(-1));
        if (JSON.stringify(current) !== JSON.stringify(dragged)) throw Error('Cancelled numeric drag changed the shape');
        if (JSON.stringify(snapshotShapes().slice(0, -1)) !== numericUntouched) throw Error('Numeric edits changed other layers');
        const frames = numericFrames.slice().sort((a, b) => a - b);
        const protectionStart = performance.now();
        await flushPendingAutosave();
        const protectedAfterMs = performance.now() - protectionStart;
        const stored = await readAutosavePayload();
        if (JSON.stringify(stored.shapes) !== JSON.stringify(snapshotShapes())) throw Error('Recovery did not preserve numeric edits exactly');
        const committed = JSON.stringify(snapshotShapes());
        await undo(); await redo();
        if (JSON.stringify(snapshotShapes()) !== committed) throw Error('Numeric drag undo/redo did not roundtrip');
        return { order, frames: frames.length, p95: frames[Math.floor(frames.length * .95)], max: Math.max(...frames), over100: frames.filter(ms => ms >= 100).length, protectedAfterMs };
      }, { order, dragged });
      rows.push(row);
    }
  } finally {
    await page.evaluate(() => { numericActive = false; cancelAnimationFrame(numericFrameHandle); });
  }
  return { ...setup, numericCommits: 96, labelDrags: 2, cancelledDrags: 2, recoveryReadbacks: 2, rows };
}
