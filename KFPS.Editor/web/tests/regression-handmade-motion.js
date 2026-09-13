async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  page.setDefaultTimeout(60000);
  const initial = await h.setup(page, output, options);
  const original = await h.snapshot(page);
  const available = await page.evaluate(() => {
    const byType = new Map();
    for (const object of vinylObjects()) {
      const key = `${object.kloudy.resource_family}/${object.kloudy.resource_index}`;
      const size = object.getScaledWidth() * object.getScaledHeight();
      const previous = byType.get(key);
      if (!previous || previous.size < size) byType.set(key, { key, size,
        id: object.kloudy.editor_id, shape: objectToShape(object) });
    }
    return [...byType.values()].sort((a, b) => a.key.localeCompare(b.key));
  });
  const targets = options.targets ? available.filter(item => options.targets.includes(item.key))
    : available.slice(options.start || 0, options.end || available.length);
  h.check(targets.length > 0, "No matching handmade targets");
  fs.writeFileSync(path.join(output, "targets.json"), JSON.stringify(targets, null, 2));
  const trace = await h.monitor(page, output);
  const cases = [];
  try {
    for (const order of options.orders || ["above", "below"]) {
      await page.locator('[data-tool-mode="overlay"]').click();
      await page.locator("#overlayLayerMode").selectOption(order);
      await page.locator('[data-tool-mode="select"]').click();
      for (const target of targets) for (const speed of options.speeds || Object.keys(h.speeds)) {
        const label = `${order}/${target.key}/${speed}`;
        if (await page.locator("#selectionLockToggle").getAttribute("aria-pressed") === "true") await page.locator("#selectionLockToggle").click();
        await h.selectId(page, target.id);
        const beforeExposure = await h.snapshot(page);
        await page.locator("#bringFront").click();
        await page.locator("#selectionLockToggle").click();
        h.check(await page.locator("#selectionLockToggle").getAttribute("aria-pressed") === "true", "Selected layer did not lock");
        const framed = await h.frameSelection(page);
        const before = await h.snapshot(page);
        const inputs = [];
        fs.writeFileSync(path.join(output, "motion-phase.json"), JSON.stringify({ label, completed: cases.length }));
        await trace.run(label, async () => {
          const geometry = await h.geometry(page), r = geometry.handles.mtr, c = geometry.center;
          const dx = r.x - c.x, dy = r.y - c.y, turn = .23;
          inputs.push(await h.motion(page, r, { x: c.x + dx * Math.cos(turn) - dy * Math.sin(turn),
            y: c.y + dx * Math.sin(turn) + dy * Math.cos(turn) }, speed));
          const rotated = await h.geometry(page);
          h.check(Math.abs(rotated.angle - geometry.angle) > 3, "Rotation did not change the real target");
          inputs.push(await h.motion(page, rotated.grab, { x: rotated.grab.x + 16, y: rotated.grab.y + 11 }, speed));
          const moved = await h.geometry(page);
          await h.expectTranslation(page,rotated,moved,16,11);
          h.check(Math.hypot(moved.left - rotated.left, moved.top - rotated.top) > .01, "Immediate move after rotation did nothing");
          await page.mouse.move(moved.center.x, moved.center.y);
          for (const delta of [-100, 100, -100, 100]) {
            await page.mouse.wheel(0, delta);
            if (speed === "slow") await page.waitForTimeout(90);
            if (speed === "ordinary") await page.waitForTimeout(25);
          }
          const zoomed = await h.geometry(page);
          inputs.push(await h.motion(page, zoomed.grab, { x: zoomed.grab.x - 13, y: zoomed.grab.y + 8 }, speed));
          const movedAgain = await h.geometry(page);
          await h.expectTranslation(page,zoomed,movedAgain,-13,8);
          h.check(Math.hypot(movedAgain.left - zoomed.left, movedAgain.top - zoomed.top) > .01, "Move after wheel did nothing");
          inputs.push(await h.motion(page, movedAgain.handles.br,
            { x: movedAgain.handles.br.x + 10, y: movedAgain.handles.br.y + 7 }, speed));
          const scaled = await h.geometry(page);
          h.check(Math.abs(scaled.scaleX - movedAgain.scaleX) + Math.abs(scaled.scaleY - movedAgain.scaleY) > 1e-6, "Corner scale did nothing");
          inputs.push(await h.motion(page, scaled.handles.br,
            { x: scaled.handles.br.x + 11, y: scaled.handles.br.y - 8 }, speed, ["Shift"]));
          const skewed = await h.geometry(page);
          h.check(Math.abs(skewed.skewX - scaled.skewX) + Math.abs(skewed.skewY - scaled.skewY) > .001, "Shift-corner skew did nothing");
          h.check(await page.evaluate(id => selectedVinylObjects().length === 1
            && selectedVinylObjects()[0].kloudy.editor_id === id, target.id), "Gesture changed the selected target");
        });
        const after = JSON.parse(await h.snapshot(page)), previous = JSON.parse(before);
        h.check(after.every((shape, i) => shape.editor_id === target.id || JSON.stringify(shape) === JSON.stringify(previous[i])), "Gesture changed unrelated handmade layers");
        for (let index = 0; index < 9 && await h.snapshot(page) !== before; index++) {
          await page.locator("#undoBtn").click();
          await page.waitForFunction(() => !editorCommands.busy);
        }
        h.check(await h.snapshot(page) === before, "Gesture chain did not undo exactly");
        if (before !== beforeExposure) await h.undo(page, beforeExposure);
        cases.push({ label, id: target.id, inputs, zoomOuts: framed.zoomOuts, exposedUsingBringToFront: true,
          exactUndo: true, exactOriginalOrder: true, unrelatedPreserved: true });
        fs.writeFileSync(path.join(output, "handmade-motion-cases.json"), JSON.stringify(cases, null, 2));
      }
    }
    if (await page.locator("#selectionLockToggle").getAttribute("aria-pressed") === "true") await page.locator("#selectionLockToggle").click();
    h.check(await h.snapshot(page) === original, "Motion matrix did not retain original artwork");
    await h.saveAs(page, "Handmade motion checkpoint");
    await page.evaluate(async () => { await flushPendingAutosave(); });
    await page.locator("#fitView").click();
    return { initial, availableTypes: available.length, targets: targets.length, cases, rows: trace.rows,
      actualLayerSelectionAndViewControls: true, selectionLockedForBuriedArtwork: true,
      exactArtwork: true, privateProjectUsed: true };
  } finally { await trace.close(); }
}
