async (page, options = {}) => {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const trace=await h.monitor(page,output);
  await page.setViewportSize({ width: 1600, height: 1000 });
  const contactCases = await page.evaluate(() => {
    const expected = { left: [10, 50], right: [90, 50], top: [50, 20], bottom: [50, 80],
      tl: [10, 20], tr: [90, 20], bl: [10, 80], br: [90, 80], center: [50, 50] };
    let count = 0;
    for (const source of ['control', 'preserved']) for (const [kind, point] of Object.entries(expected)) {
      const actual = axisSnapPoints({ left: 10, top: 20, width: 80, height: 60 }, { kind, source });
      if (actual.xPoints[0].value !== point[0] || actual.yPoints[0].value !== point[1]) throw Error(`Wrong axis contact: ${source}/${kind}`);
      count++;
    }
    return count;
  });
  const cases = [];
  const masked = Boolean(options.mask);
  const types = masked ? [1048677] : [1048677, 1048678];
  const angles = masked ? [17] : [0, 17];
  let handmade = null;
  try {for (const type of types) for (const angle of angles) {
    if (options.project) {
      if (!handmade) handmade = await h.setup(page, output, { ...options, layers: 2950 });
      await require(path.join(__dirname, "handmade-project-fixture.cjs")).selectId(page, "dense-other");
      await page.locator("#shapePlacementMode").selectOption("replace");
      await page.locator('[data-tool-mode="shapeLibrary"]').click();
      await page.locator("#shapeFamily").selectOption("Primitives");
      await h.type(page, "#shapeSearch", String(type));
      await page.locator("#shapeGrid .shapeTile img").first().click();
      await page.waitForFunction(type => selectedVinylObjects()[0]?.kloudy.type === type, type);
      await page.locator('[data-tool-mode="select"]').click();
      for (const [field, value] of [["xInput", 0], ["yInput", 0], ["sxInput", 1.6], ["syInput", 1.2], ["rotInput", angle]]) {
        await h.type(page, `#${field}`, value); await page.locator(`#${field}`).press("Enter");
      }
      if (masked && !await page.evaluate(() => selectedVinylObjects()[0].kloudy.mask)) await page.locator("#maskSelectedTool").click();
      await page.evaluate(() => { window.contactUntouched = JSON.stringify(snapshotShapes().slice(0, -1)); });
    } else await page.evaluate(async ({ type, angle, masked }) => {
      await loadPayload({ shapes: Array.from({ length: 3000 }, (_, index) => ({
        type: index === 2999 ? type : 1048677, color: [80, 160, 220, 255],
        mask: index === 2999 && masked,
        data: index === 2999 ? [0, 0, 1.6, 1.2, angle, 0, 0] : [-270 + index % 60 * 9, 185 - Math.floor(index / 60) * 7.5, .07, .07, 0, 0, 0],
      })) });
      const source = document.createElement('canvas'); source.width = 6000; source.height = 4000;
      const context = source.getContext('2d'); context.fillStyle = '#60776f'; context.fillRect(0, 0, source.width, source.height);
      await editorReference.loadOverlayImageFromUrl(source.toDataURL(), 'guide-contact-reference.png');
      source.width = source.height = 1;
      window.contactUntouched = JSON.stringify(snapshotShapes().slice(0, -1));
    }, { type, angle, masked });
    await page.locator('[data-tool-mode="select"]').click();
    for (const side of ['left', 'right', 'top', 'bottom']) for (const degrees of [0, 45, 90]) for (const snap of [false, true]) {
      const label = `${type}/${angle}/${side}/${degrees}/${snap ? 'Control' : 'plain'}`;
      await trace.run(label,async()=> {
      const setup = await page.evaluate(({ side, degrees }) => {
        const target = vinylObjects().at(-1);
        selectObjects([target], 'guide-contact matrix fixture');
        canvas.setViewportTransform([1.5, 0, 0, 1.5, canvas.width / 2, canvas.height / 2]);
        const coords = objectCornerCoords(target), contact = coords[side];
        const radians = degrees * Math.PI / 180;
        const tangent = { x: Math.cos(radians), y: Math.sin(radians) };
        const normal = { x: -tangent.y, y: tangent.x };
        const destination = { x: contact.x + normal.x * 25, y: contact.y + normal.y * 25 };
        const line = { id: 'contact-line', x1: destination.x - tangent.x * 400,
          y1: destination.y - tangent.y * 400, x2: destination.x + tangent.x * 400,
          y2: destination.y + tangent.y * 400, constraint: 'free' };
        applySavedGuideState(null);
        guideState.gridEnabled = false; guideState.snapCtrlOnly = true;
        guideState.guides = [line]; renderGuideObjects();
        window.contactEvents = [];
        if (window.contactObserver) canvas.off('object:moving', window.contactObserver);
        window.contactObserver = event => {
          if (contactEvents.length >= 16) return;
          contactEvents.push({ ctrl: eventHasSnapModifier(event), contact: guideContactForTarget(event.target, event)?.kind,
            guides: guideSnapLines(), snapshot: transformAnchorSnapshot?.contactKind,
            selected: selectedVinylObjects().length, left: event.target.left, top: event.target.top, angle: event.target.angle });
        };
        canvas.on('object:moving', window.contactObserver);
        setOverlayLayerMode(degrees === 45 ? 'above' : 'below');
        target.setCoords(); canvas.renderAll();
        const rect = canvas.upperCanvasEl.getBoundingClientRect();
        const toScreen = point => {
          const p = fabric.util.transformPoint(new fabric.Point(point.x, point.y), canvas.viewportTransform);
          return { x: p.x + rect.left, y: p.y + rect.top };
        };
        // Grab inside the geometry, clear of the outside resize handles.
        const start = { x: contact.x * .90 + coords.center.x * .10, y: contact.y * .90 + coords.center.y * .10 };
        return { start: toScreen(start), end: toScreen({ x: start.x + normal.x * 23, y: start.y + normal.y * 23 }),
          before: objectToShape(target), line };
      }, { side, degrees });
      try {
        await page.mouse.move(setup.start.x, setup.start.y);
        if (snap) await page.keyboard.down('Control');
        await page.mouse.down();
        await page.mouse.move(setup.end.x, setup.end.y, { steps: 12 });
        if (snap) {
          const dx = setup.end.x - setup.start.x, dy = setup.end.y - setup.start.y;
          await page.mouse.move(setup.end.x + dx * 3, setup.end.y + dy * 3, { steps: 8 });
          const escaped = await page.evaluate(({ side, line }) => {
            const point = objectCornerCoords(vinylObjects().at(-1))[side];
            const dx = line.x2 - line.x1, dy = line.y2 - line.y1;
            return Math.abs(dx * (point.y - line.y1) - dy * (point.x - line.x1)) / Math.hypot(dx, dy);
          }, { side, line: setup.line });
          if (escaped < 35) throw Error(`${label}: snapped guide trapped the drag (${escaped})`);
          await page.mouse.move(setup.end.x, setup.end.y, { steps: 8 });
        }
        await page.mouse.up();
      } finally {
        await page.mouse.up(); await page.keyboard.up('Control');
      }
      const distance = await page.evaluate(({ side, line }) => {
        const target = vinylObjects().at(-1);
        const point = objectCornerCoords(target)[side];
        const dx = line.x2 - line.x1, dy = line.y2 - line.y1;
        const distance = Math.abs(dx * (point.y - line.y1) - dy * (point.x - line.x1)) / Math.hypot(dx, dy);
        if (JSON.stringify(snapshotShapes().slice(0, -1)) !== contactUntouched) throw Error('Guide snap changed unrelated shapes');
        return distance;
      }, { side, line: setup.line });
      const events = await page.evaluate(() => { canvas.off('object:moving', window.contactObserver); return contactEvents; });
      if (snap ? distance > .05 : distance < .5) {
        fs.writeFileSync(path.join(output, 'guide-contact-failure.json'), JSON.stringify({ label, setup, distance, events }, null, 2));
        throw Error(`${label}: modifier/side snap mismatch (distance ${distance})`);
      }
      await page.locator('#undoBtn').click();
      await page.waitForFunction(before => JSON.stringify(objectToShape(vinylObjects().at(-1))) === JSON.stringify(before), setup.before);
      cases.push({ label, distance, exactUndo: true });
      fs.writeFileSync(path.join(output, 'guide-contact-matrix.json'), JSON.stringify(cases, null, 2));
      });
    }
  }} finally {await trace.close();}
  if(!handmade && trace.rows.some(row=>row.after.visible<2700))throw Error('Guide contact fixture lost dense visibility');
  if(handmade && trace.rows.some(row=>row.after.layers!==2950))throw Error('Guide contact fixture lost handmade layers');
  await page.evaluate(async () => {
    await flushPendingAutosave();
    if (JSON.stringify((await readAutosavePayload()).shapes) !== JSON.stringify(snapshotShapes())) throw Error('Guide contact recovery differs');
  });
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Guide contact checkpoint');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  return { cases: cases.length, rows:trace.rows,contactCases, layers: handmade ? 2950 : 3000, handmade,
    controlledGuideSetup: true, masked, sides: 4, guideAngles: [0, 45, 90], shapeAngles: angles, reference: true, escapeAndReturn: true, exactUndoAndRecovery: true };
}
