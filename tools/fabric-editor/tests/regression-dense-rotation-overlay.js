// Requires the private 3,000-shape transition fixture in a reused native profile.
async page => {
  await page.waitForFunction(() => vinylObjects().length === 3000 && overlayImage);
  const expectMissing = process.env.KFPS_EXPECT_MISSING_RING === '1';
  const evidence = [];
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const geometry = () => page.evaluate(() => {
    const target = canvas.getActiveObject();
    if (!target?.kloudy?.editor_id.startsWith('target-')) throw new Error('Wrong rotation target');
    const bounds = canvas.upperCanvasEl.getBoundingClientRect();
    const center = fabric.util.transformPoint(target.getCenterPoint(), canvas.viewportTransform);
    const ring = rotationNotchMetrics(target);
    return { center: { x: bounds.left + center.x, y: bounds.top + center.y },
      handle: { x: bounds.left + target.oCoords.mtr.x, y: bounds.top + target.oCoords.mtr.y },
      radius: ring.radius * canvas.getZoom(), angle: target.angle, id: target.kloudy.editor_id };
  });
  const sample = () => page.evaluate(() => {
    const target = canvas.getActiveObject(), ring = rotationNotchMetrics(target);
    const context = canvas.contextTop, ratio = canvas.getRetinaScaling();
    const inkAt = point => {
      const p = fabric.util.transformPoint(point, canvas.viewportTransform);
      const x = Math.round(p.x * ratio), y = Math.round(p.y * ratio);
      if (x < 4 || y < 4 || x >= context.canvas.width - 4 || y >= context.canvas.height - 4) return -1;
      const pixels = context.getImageData(x - 3, y - 3, 7, 7).data;
      let ink = 0;
      for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 12) ink++;
      return ink;
    };
    const ticks = Array.from({ length: 8 }, (_, index) => {
      const a = index * Math.PI / 4, length = index % 2 ? ring.tickMinor : ring.tickMajor;
      return inkAt({ x: ring.center.x + Math.cos(a) * (ring.radius - length / 2),
        y: ring.center.y + Math.sin(a) * (ring.radius - length / 2) });
    });
    const control = target.oCoords.mr;
    const inverse = fabric.util.invertTransform(canvas.viewportTransform);
    return { ticks, controlInk: inkAt(fabric.util.transformPoint(control, inverse)),
      snapHelpers: snapOverlayObjects.length, active: hybridRenderActive,
      lowerHidden: canvas.lowerCanvasEl.style.visibility === 'hidden', angle: target.angle,
      layerCount: vinylObjects().length, referenceMode: overlayLayerMode,
      focus: document.hasFocus(), transform: canvas._currentTransform?.action };
  });
  for (const mode of ['below', 'above']) for (const slot of [30, 36, 39]) {
    await page.locator('[data-panel="overlayPane"]').click();
    await page.locator('#overlayLayerMode').selectOption(mode);
    await page.locator('#layerSearch').fill(`Transition target ${slot}`);
    await page.locator('.layerRow').filter({ hasText: `Transition target ${slot}` }).click();
    await page.locator('#fitView').click();
    const start = await geometry();
    const initial = Math.atan2(start.handle.y - start.center.y, start.handle.x - start.center.x);
    await page.mouse.move(start.handle.x, start.handle.y);
    await page.mouse.down();
    for (const angle of [45, 90, 135, 180, 225, 270, 315, 0]) {
      const direction = initial + (angle - start.angle) * Math.PI / 180;
      await page.mouse.move(start.center.x + Math.cos(direction) * start.radius,
        start.center.y + Math.sin(direction) * start.radius, { steps: 3 });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const state = await sample();
      if (!state.active || !state.lowerHidden || state.snapHelpers !== 10 || state.transform !== 'rotate') {
        throw new Error('Did not exercise GPU rotation: ' + JSON.stringify(state));
      }
      if (Math.abs(((state.angle - angle + 540) % 360) - 180) > .01) throw new Error('45-degree notch did not snap: ' + JSON.stringify(state));
      if (!expectMissing && (state.ticks.some(value => value <= 0) || state.controlInk <= 0)) {
        throw new Error('Interaction overlays are not visible: ' + JSON.stringify(state));
      }
      if (angle === 45) await page.screenshot({ path: path.join(output, `rotation-${mode}-${slot}.png`) });
      evidence.push({ mode, slot, notch: angle, ...state });
      if (expectMissing) break;
    }
    await page.mouse.up();
    await page.waitForFunction(() => snapOverlayObjects.length === 0 && !hybridRenderActive);
    const cleared = await page.evaluate(() => {
      const pixels = canvas.contextTop.getImageData(0, 0, canvas.contextTop.canvas.width, canvas.contextTop.canvas.height).data;
      let ink = 0;
      for (let i = 3; i < pixels.length; i += 4) if (pixels[i]) ink++;
      return ink;
    });
    if (cleared) throw new Error('Rotation overlay left stale pixels after release: ' + cleared);
  }
  await page.locator('#layerSearch').fill('');
  await page.locator('#saveProject').click();
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(() => flushPendingAutosave());
  fs.writeFileSync(path.join(output, 'rotation-overlay-evidence.json'), JSON.stringify(evidence, null, 2));
  if (errors.length) throw new Error(errors.join('\n'));
  return { expectMissing, loaded: 3000, cases: evidence.length, evidence };
}
