async page => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.evaluate(async () => {
    await loadPayload({ shapes: [{type: 1048706, color: [70, 140, 220, 255], data: [0, 0, 2, 2, 25, 0, 0]}] });
    const source = document.createElement("canvas"); source.width = 2400; source.height = 1600;
    const ctx = source.getContext("2d"); ctx.fillStyle = "#92a5b0"; ctx.fillRect(0, 0, 2400, 1600);
    ctx.fillStyle = "#e7f0f0"; ctx.fillRect(200, 200, 1800, 60);
    await loadOverlayImageFromUrl(source.toDataURL(), "guide-reference.png");
    source.width = source.height = 1;
    canvas.setViewportTransform([1, 0, 0, 1, canvas.width / 2, canvas.height / 2]);
    window.guideOriginalShapes = JSON.stringify(vinylObjects().map(o => objectToShape(o)));
  });
  await page.locator('[data-tool-mode="guides"]').click();
  await page.locator("#guideConstraint").selectOption("free");
  await page.locator("#snapGuideAnchor").uncheck();
  await page.locator("#snapGuideEnd").uncheck();
  const box = await page.locator(".upper-canvas").boundingBox();
  const a = { x: box.x + box.width * .3, y: box.y + box.height * .3 };
  const b = { x: a.x + 120, y: a.y + 90 };
  const state = () => page.evaluate(() => ({draft: guideDraft && {...guideDraft}, guides: cloneGuidesForSave(), pan: isPanning, view: canvas.viewportTransform.slice()}));
  await page.mouse.click(a.x, a.y);
  const start = await state();
  assert(start.draft && !start.guides.length, "First click must retain an anchor");
  await page.evaluate(() => { window.initialGuideHelper = guideDraftObject; });
  await page.mouse.move(b.x, b.y);
  assert(await page.evaluate(() => guideDraftObject === initialGuideHelper), "Pointer movement rebuilt the draft helper");
  await page.locator("#snapGuideEnd").check();
  assert((await state()).draft, "Changing settings lost the guide draft");
  await page.locator("#snapGuideEnd").uncheck();
  await page.mouse.move(b.x, b.y);
  await page.mouse.wheel(0, -450);
  await page.waitForTimeout(100);
  const zoomed = await state();
  assert(zoomed.view[0] !== start.view[0] && zoomed.draft.x1 === start.draft.x1 && zoomed.draft.y1 === start.draft.y1, "Wheel moved or lost guide anchor");
  for (const button of ["right", "middle"]) {
    const before = await state();
    await page.mouse.down({button});
    await page.mouse.move(b.x + 60, b.y + 25, {steps: 6});
    await page.mouse.up({button});
    const after = await state();
    assert(await page.evaluate(() => document.activeElement === canvas.upperCanvasEl), "Guide input retained keyboard focus after canvas gesture");
    assert(!after.pan && after.draft && !after.guides.length, `${button} pan completed/lost draft`);
    assert(after.view[4] !== before.view[4] && after.draft.x1 === start.draft.x1, `${button} pan failed`);
    await page.mouse.move(b.x, b.y);
  }
  await page.keyboard.down("Space");
  await page.mouse.move(b.x + 35, b.y + 35, {steps: 4});
  await page.keyboard.up("Space");
  await page.waitForFunction(() => !isPanning);
  assert((await state()).draft && !(await state()).pan, "Space pan lost draft or stayed active");
  await page.keyboard.down("Shift");
  await page.mouse.move(b.x + 150, b.y + 125, {steps: 6});
  const constrained = await state();
  const d = constrained.draft;
  const angle = Math.atan2(d.y2 - d.y1, d.x2 - d.x1) * 180 / Math.PI;
  assert(Math.abs(angle / 45 - Math.round(angle / 45)) < 1e-6, "Pointer Shift did not constrain to 45 degrees: " + JSON.stringify(constrained));
  await page.mouse.click(b.x + 150, b.y + 125);
  await page.keyboard.up("Shift");
  assert(!(await state()).draft && (await state()).guides.length === 1, "Second click did not commit exactly one guide");
  await page.evaluate(async () => { await undo(); });
  assert(!(await state()).guides.length, "Undo guide");
  await page.evaluate(async () => { await redo(); });
  assert((await state()).guides.length === 1, "Redo guide");

  // Traditional drag, including navigation with both mouse buttons held.
  await page.mouse.move(a.x - 60, a.y + 100); await page.mouse.down();
  await page.mouse.move(a.x + 40, a.y + 160, {steps: 5});
  await page.mouse.wheel(0, 200); await page.waitForTimeout(70);
  await page.mouse.down({button: "right"});
  await page.mouse.move(a.x + 90, a.y + 185, {steps: 4});
  await page.mouse.up({button: "right"}); await page.mouse.up();
  assert((await state()).draft && (await state()).guides.length === 1, "Intermediate button release committed draft");
  await page.keyboard.press("Escape");
  assert(!(await state()).draft && !(await state()).pan, "Escape cancellation");
  await page.mouse.move(a.x - 50, a.y + 120); await page.mouse.down();
  await page.mouse.move(a.x + 80, a.y + 220, {steps: 12}); await page.mouse.up();
  assert((await state()).guides.length === 2, "Traditional drag broke");
  await page.mouse.click(a.x, a.y);
  await page.locator('[data-tool-mode="select"]').click();
  assert(!(await state()).draft, "Switching tools kept a stale draft");

  const geometryCases = await page.evaluate(() => {
    const saved = savedGuideState(); let count = 0;
    for (const grid of [false, true]) for (const constraint of ["free", "horizontal", "vertical"]) {
      guideState.snapGuideEnd = grid; guideState.guideConstraint = constraint;
      for (let deg = -179; deg < 180; deg += 7) {
        const a = {x: 13, y: -17}, p = {x: 13 + 151 * Math.cos(deg * Math.PI / 180), y: -17 + 151 * Math.sin(deg * Math.PI / 180)};
        const e = constrainedGuideEnd(a, p, {shiftKey: true});
        const angle = Math.atan2(e.y - a.y, e.x - a.x) / (Math.PI / 4);
        if (Math.abs(angle - Math.round(angle)) > 1e-8 || !Number.isFinite(angle)) throw new Error("Angle matrix " + deg);
        if (constraint === "horizontal" && e.y !== a.y || constraint === "vertical" && e.x !== a.x) throw new Error("Explicit axis overridden");
        count++;
      }
    }
    Object.assign(guideState, saved); applyGuideStateToUi();
    if (guideOriginalShapes !== JSON.stringify(vinylObjects().map(o => objectToShape(o)))) throw new Error("Guides changed artwork");
    return count;
  });
  const completed = (await state()).guides;
  await page.locator('[data-tool-mode="guides"]').click();
  const points = await page.evaluate(() => {
    guideState.guides = [{id:"diagonal-hit-test", x1:-150,y1:-150,x2:150,y2:150,constraint:"free"}];
    renderGuideObjects();
    const rect = canvas.upperCanvasEl.getBoundingClientRect();
    const screen = p => { const q = fabric.util.transformPoint(new fabric.Point(...p),canvas.viewportTransform); return {x:q.x+rect.left,y:q.y+rect.top}; };
    return {empty:screen([100,-100]), line:screen([0,0])};
  });
  await page.mouse.click(points.empty.x,points.empty.y);
  assert((await state()).draft, "Diagonal bounding box captured empty canvas");
  await page.keyboard.press("Escape");
  await page.mouse.click(points.line.x,points.line.y);
  assert(await page.evaluate(() => selectedGuideId === "diagonal-hit-test" && !guideDraft), "Clicking the guide itself failed to select it");
  await page.mouse.click(points.empty.x,points.empty.y);
  await page.evaluate(() => applySavedGuideState(null));
  assert(!(await state()).draft && !(await state()).pan, "Document restore retained guide gesture");
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setTouchEmulationEnabled", {enabled:true,maxTouchPoints:1});
  try {
    await cdp.send("Input.dispatchTouchEvent", {type:"touchStart",touchPoints:[{x:a.x,y:a.y}]});
    await cdp.send("Input.dispatchTouchEvent", {type:"touchMove",touchPoints:[{x:a.x+80,y:a.y+80}]});
    await cdp.send("Input.dispatchTouchEvent", {type:"touchEnd",touchPoints:[]});
    const touch = await state();
    assert(!touch.draft && touch.guides.length===1 && Number.isFinite(touch.guides[0].x2), "Touch guide drawing regressed");
  } finally {
    await cdp.send("Emulation.setTouchEmulationEnabled", {enabled:false});
    await cdp.detach();
  }
  await page.locator('[data-tool-mode="select"]').click();
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Guide navigation regression');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  return { geometryCases, guides: completed, reference: true, pointerNavigation: true, preciseGuidePicking: true, touchDrag:true };
}
