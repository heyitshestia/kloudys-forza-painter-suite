// Run through playwright-cli run-code --filename against an isolated editor server.
async (page) => {
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.evaluate(async () => {
    document.querySelectorAll('dialog[open]').forEach(d => d.close());
    window.testShape = (i = 0, mask = false) => ({
      type: 1048677, type_word: 101, resource_family: 'Primitives', resource_index: 1,
      color: [55 + i * 20, 135, 210, 255], data: [i * 220, 0, 1, 1, 0, 0, mask ? 1 : 0],
    });
    window.testSetup = async (props = {}, mask = false) => {
      await loadPayload({ shapes: [testShape(0, mask), testShape(1)] });
      const o = vinylObjects()[0];
      o.set({ ...props });
      syncMaskPreviewOutlines();
      canvas.setActiveObject(mask ? maskPreviewOutlines.get(o) : o);
      updateSelectionPanel();
      await Promise.all([...selectionOutlinePathPromises.values()]);
      canvas.setZoom(1);
      canvas.absolutePan(new fabric.Point(-canvas.getWidth() / 2, -canvas.getHeight() / 2));
      canvas.getActiveObject().setCoords();
      canvas.renderAll();
      return o;
    };
    window.testAssert = (ok, message) => { if (!ok) throw new Error(message); };
    window.testNear = (a, b, message) => testAssert(Math.abs(a - b) < 0.00005, `${message}: ${a} != ${b}`);
    window.testHelpers = () => {
      const objects = canvas.getObjects();
      const outlines = objects.filter(o => o.kloudySelectionOutlineHelper);
      testAssert(outlines.length === selectedShapeOutlineHelpers.size, 'orphan selection outline');
      for (const [owner, helper] of selectedShapeOutlineHelpers) {
        testAssert(objects.includes(owner) && objects.includes(helper), 'detached selection helper');
      }
      for (const map of [maskPreviewCutouts, maskPreviewOutlines]) {
        for (const [owner, helper] of map) testAssert(objects.includes(owner) && objects.includes(helper), 'detached mask helper');
      }
      return { layers: vinylObjects().length, outlines: outlines.length, masks: maskPreviewOutlines.size };
    };
  });

  // Exercise real Fabric matrices, locks, flips and event hooks across both axes.
  const matrixCases = await page.evaluate(async () => {
    let count = 0;
    const o = await testSetup();
    for (const skew of [[0, 0], [40, 0], [-50, 0], [0, 30], [35, -20]]) {
      for (const flips of [[false, false], [true, false], [false, true], [true, true]]) {
        for (const corner of ['ml', 'mr', 'mt', 'mb']) {
          for (const centered of [false, true]) {
            o.set({ left: 0, top: 0, scaleX: 1.3, scaleY: 0.8, angle: 27, skewX: skew[0], skewY: skew[1], flipX: flips[0], flipY: flips[1] });
            const before = o.calcOwnMatrix().slice();
            const xAxis = corner === 'ml' || corner === 'mr';
            const side = (corner === 'mr' || corner === 'mb' ? 1 : -1) * ((xAxis ? o.flipX : o.flipY) ? -1 : 1);
            const dimension = xAxis ? o.width : o.height;
            const localDelta = side * dimension * 0.25 / (centered ? 2 : 1);
            const delta = fabric.util.transformPoint(new fabric.Point(xAxis ? localDelta : 0, xAxis ? 0 : localDelta), before, true);
            const transform = { target: o, corner, ex: 0, ey: 0, originX: centered || !xAxis ? 'center' : (side > 0 ? 'left' : 'right'), originY: centered || xAxis ? 'center' : (side > 0 ? 'top' : 'bottom') };
            testAssert(o.controls[corner].actionHandler({}, transform, delta.x, delta.y), 'resize did not change');
            const after = o.calcOwnMatrix();
            for (let i = 0; i < 4; i++) testNear(after[i], before[i] * ((xAxis ? i < 2 : i >= 2) ? 1.25 : 1), `${corner} edge basis`);
            const anchor = new fabric.Point(!centered && xAxis ? -side * o.width / 2 : 0, !centered && !xAxis ? -side * o.height / 2 : 0);
            const fixed = fabric.util.transformPoint(anchor, before);
            const actual = fabric.util.transformPoint(anchor, after);
            testNear(actual.x, fixed.x, 'anchor x'); testNear(actual.y, fixed.y, 'anchor y');
            testAssert(!o.controls[corner].actionHandler({}, transform, delta.x, delta.y), 'identical pointer should be a no-op');
            count++;
          }
        }
      }
    }
    for (const corner of ['mr', 'mb']) {
      const xAxis = corner === 'mr';
      for (const locked of [false, true]) {
        o.set({ left: 0, top: 0, scaleX: 1, scaleY: 1, angle: 0, skewX: 35, skewY: 0, flipX: false, flipY: false, lockScalingFlip: locked });
        const m = o.calcOwnMatrix().slice();
        const delta = fabric.util.transformPoint(new fabric.Point(xAxis ? -1.5 * o.width : 0, xAxis ? 0 : -1.5 * o.height), m, true);
        const t = { target: o, corner, ex: 0, ey: 0, originX: xAxis ? 'left' : 'center', originY: xAxis ? 'center' : 'top' };
        o.controls[corner].actionHandler({}, t, delta.x, delta.y);
        testAssert((xAxis ? o.flipX : o.flipY) === !locked, 'flip lock');
        testAssert(o.calcOwnMatrix().every(Number.isFinite), 'finite crossing transform');
        count++;
      }
      o.set(xAxis ? 'lockScalingX' : 'lockScalingY', true);
      const before = o.calcOwnMatrix().slice();
      testAssert(!o.controls[corner].actionHandler({}, { target: o }, 50, 50), 'axis lock ignored');
      testAssert(o.calcOwnMatrix().every((v, i) => v === before[i]), 'locked object changed');
      o.set(xAxis ? 'lockScalingX' : 'lockScalingY', false);
      count++;
    }
    return count;
  });

  const cornerCases = await page.evaluate(async () => {
    const o = await testSetup();
    let count = 0;
    const corners = ['tl', 'tr', 'bl', 'br'];
    for (const skew of [[0, 0], [40, 0], [-55, 0], [35, 20]]) {
      for (const flips of [[false, false], [true, false], [false, true], [true, true]]) {
        for (const corner of corners) {
          for (const centered of [false, true]) {
            o.set({left:10,top:20,scaleX:1.3,scaleY:0.7,angle:32,skewX:skew[0],skewY:skew[1],flipX:flips[0],flipY:flips[1],lockSkewingX:false,lockScalingFlip:false});
            const before = o.calcOwnMatrix().slice();
            const t = {target:o,corner,ex:300,ey:250};
            const e = {shiftKey:true,altKey:centered};
            const handler = o.controls[corner].actionHandler;
            testAssert(!handler(e,t,300,250), 'skew changed at grab');
            before.forEach((v,i) => testNear(o.calcOwnMatrix()[i],v,'skew grab matrix'));
            const a = fabric.util.degreesToRadians(o.angle);
            const dx = Math.cos(a), dy = Math.sin(a);
            testAssert(handler(e,t,300+dx,250+dy), 'skew ignored one-pixel move');
            const after = o.calcOwnMatrix();
            const sx = (corner.endsWith('r') ? 1 : -1) * (flips[0] ? -1 : 1);
            const sy = (corner.startsWith('b') ? 1 : -1) * (flips[1] ? -1 : 1);
            const grab = new fabric.Point(sx*o.width/2,sy*o.height/2);
            const anchor = centered ? new fabric.Point(0,0) : new fabric.Point(grab.x,-grab.y);
            const oldGrab = fabric.util.transformPoint(grab,before);
            const newGrab = fabric.util.transformPoint(grab,after);
            testNear(newGrab.x-oldGrab.x,dx,'skew follows x delta'); testNear(newGrab.y-oldGrab.y,dy,'skew follows y delta');
            const oldAnchor = fabric.util.transformPoint(anchor,before);
            const newAnchor = fabric.util.transformPoint(anchor,after);
            testNear(newAnchor.x,oldAnchor.x,'skew anchor x'); testNear(newAnchor.y,oldAnchor.y,'skew anchor y');
            testNear(o.scaleX,1.3,'skew scale x'); testNear(o.scaleY,0.7,'skew scale y');
            handler(e,t,300,250);
            before.forEach((v,i) => testNear(o.calcOwnMatrix()[i],v,'skew returns to start'));
            // Changing mode at the same pointer must not normalize or jump.
            testAssert(!handler({shiftKey:false,altKey:centered},t,300,250),'release shift jump');
            const scaleAnchor = centered ? new fabric.Point(0,0) : new fabric.Point(-grab.x,-grab.y);
            const direction = fabric.util.transformPoint(grab.subtract(scaleAnchor),before,true);
            handler({shiftKey:false,altKey:centered},t,300+direction.x*0.25,250+direction.y*0.25);
            const scaled = o.calcOwnMatrix().slice();
            for(let i=0;i<4;i++) testNear(scaled[i],before[i]*1.25,'uniform corner scaling');
            testAssert(!handler({shiftKey:true,altKey:centered},t,300+direction.x*0.25,250+direction.y*0.25),'press shift jump');
            scaled.forEach((v,i) => testNear(o.calcOwnMatrix()[i],v,'mode switch matrix'));
            count++;
          }
        }
      }
    }
    o.lockSkewingX = true;
    testAssert(!o.controls.tr.actionHandler({shiftKey:true},{target:o,corner:'tr',ex:0,ey:0},30,0),'skew lock');
    o.lockSkewingX = false;
    return count+1;
  });

  // Real mouse drags include displaced handle hit boxes and viewport transforms.
  const pointerCases = [];
  for (const [corner, angle, flipX, mask, zoom] of [
    ['mr', 0, false, false, 1], ['ml', 25, true, false, 0.7],
    ['mt', -25, false, false, 1.4], ['mb', 20, false, true, 1],
  ]) {
    const start = await page.evaluate(async ({ corner, angle, flipX, mask, zoom }) => {
      const owner = await testSetup({ skewX: 40, angle, flipX }, mask);
      canvas.zoomToPoint(new fabric.Point(canvas.getWidth() / 2, canvas.getHeight() / 2), zoom);
      const o = canvas.getActiveObject(); o.setCoords();
      const m = o.calcOwnMatrix().slice();
      const xAxis = corner === 'ml' || corner === 'mr';
      const side = (corner === 'mr' || corner === 'mb' ? 1 : -1) * ((xAxis ? o.flipX : o.flipY) ? -1 : 1);
      const delta = fabric.util.transformPoint(new fabric.Point(xAxis ? side * o.width * 0.25 : 0, xAxis ? 0 : side * o.height * 0.25), m, true);
      const r = canvas.upperCanvasEl.getBoundingClientRect();
      return { m, owner: owner.calcOwnMatrix().slice(), xAxis, x: r.left + o.oCoords[corner].x, y: r.top + o.oCoords[corner].y, dx: delta.x * zoom, dy: delta.y * zoom };
    }, { corner, angle, flipX, mask, zoom });
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(start.x + start.dx, start.y + start.dy, { steps: 8 });
    await page.mouse.up();
    pointerCases.push(await page.evaluate(({ start, corner }) => {
      const owner = selectedVinylObjects()[0];
      const m = owner.calcOwnMatrix();
      for (let i = 0; i < 4; i++) {
        const changed = start.xAxis ? i < 2 : i >= 2;
        const expected = start.owner[i] * (changed ? 1.25 : 1);
        // Browser mouse coordinates are quantized; untouched edge vectors are exact.
        testAssert(Math.abs(m[i] - expected) < (changed ? 0.005 : 0.00005), `pointer ${corner}: ${m[i]} != ${expected}`);
      }
      testHelpers();
      return { corner, matrix: m };
    }, { start, corner }));
  }

  const cornerDrags = [];
  for (const [corner,skewX,angle,flipX,flipY,zoom,mask,scaleX=0.8,scaleY=0.9,multi=false] of [
    ['tr',40,0,false,false,1,false], ['tl',-40,30,true,false,0.7,false],
    ['br',0,-20,false,true,1.3,true], ['bl',50,25,true,true,0.7,false],
    ['tr',45,12,false,false,1,false,0.12,0.1],
    ['tr',25,10,false,false,1,false,0.8,0.9,true],
  ]) {
    const start = await page.evaluate(async spec => {
      const {corner,skewX,angle,flipX,flipY,zoom,mask,scaleX,scaleY,multi} = spec;
      await testSetup({skewX,angle,flipX,flipY,scaleX,scaleY},mask);
      if (multi) { canvas.setActiveObject(styledActiveSelection(vinylObjects())); canvas.getActiveObject().set({skewX,angle}); }
      pushHistory('skew fixture');
      canvas.zoomToPoint(new fabric.Point(canvas.width/2,canvas.height/2),zoom);
      const o=canvas.getActiveObject(); o.setCoords();
      const r=canvas.upperCanvasEl.getBoundingClientRect();
      return {x:r.left+o.oCoords[corner].x,y:r.top+o.oCoords[corner].y,matrix:o.calcOwnMatrix().slice()};
    },{corner,skewX,angle,flipX,flipY,zoom,mask,scaleX,scaleY,multi});
    await page.mouse.move(start.x,start.y); await page.keyboard.down('Shift'); await page.mouse.down();
    await page.evaluate(start => start.matrix.forEach((v,i) => testNear(canvas.getActiveObject().calcOwnMatrix()[i],v,'pointer skew grab')),start);
    await page.mouse.move(start.x+1,start.y,{steps:1});
    const first = await page.evaluate(({start,zoom}) => {
      const m=canvas.getActiveObject().calcOwnMatrix();
      testAssert(Math.hypot(m[4]-start.matrix[4],m[5]-start.matrix[5])*zoom < 2,'first pixel jumped');
      testAssert(Math.max(...m.slice(0,4).map((v,i)=>Math.abs(v-start.matrix[i]))) < 0.05,'first pixel changed skew discontinuously');
      return m;
    },{start,zoom});
    await page.mouse.move(start.x+30,start.y,{steps:5});
    const skewed = await page.evaluate(() => canvas.getActiveObject().calcOwnMatrix().slice());
    await page.keyboard.up('Shift'); await page.mouse.move(start.x+30,start.y,{steps:1});
    await page.evaluate(before => before.forEach((v,i)=>testNear(canvas.getActiveObject().calcOwnMatrix()[i],v,'real shift release')),skewed);
    await page.mouse.move(start.x+40,start.y+10,{steps:3});
    const scaled = await page.evaluate(() => canvas.getActiveObject().calcOwnMatrix().slice());
    await page.keyboard.down('Shift'); await page.mouse.move(start.x+40,start.y+10,{steps:1});
    await page.evaluate(before => before.forEach((v,i)=>testNear(canvas.getActiveObject().calcOwnMatrix()[i],v,'real shift press')),scaled);
    await page.mouse.up(); await page.keyboard.up('Shift');
    await page.evaluate(async () => {
      testHelpers();
      const matrices=vinylObjects().map(o=>o.calcTransformMatrix().slice());
      const payload=editableProjectPayload('skew-roundtrip');
      await loadProjectPayload(payload,'skew-roundtrip');
      vinylObjects().forEach((o,i)=>o.calcTransformMatrix().forEach((v,j)=>testNear(v,matrices[i][j],'skew project roundtrip')));
      testHelpers();
    });
    cornerDrags.push({corner,first});
  }

  const interruptedDrags = [];
  for (const kind of ['move', 'resize', 'mask', 'selection', 'floor', 'skew']) {
    const start = await page.evaluate(async kind => {
      const o = await testSetup({ skewX: kind === 'floor' ? 0 : 25 }, kind === 'mask');
      if (kind !== 'floor') o.set('left', 20);
      syncMaskPreviewOutlines();
      if (kind === 'selection') canvas.setActiveObject(styledActiveSelection(vinylObjects()));
      if (kind !== 'floor') pushHistory('drag fixture');
      const target = canvas.getActiveObject(); target.setCoords();
      const r = canvas.upperCanvasEl.getBoundingClientRect();
      const p = kind === 'resize' ? target.oCoords.mr : (kind === 'skew' ? target.oCoords.tr : fabric.util.transformPoint(target.getCenterPoint(), canvas.viewportTransform));
      return { x: r.left + p.x, y: r.top + p.y, matrices: vinylObjects().map(o => o.calcTransformMatrix()), index: historyIndex };
    }, kind);
    await page.mouse.move(start.x, start.y);
    if (kind === 'skew') await page.keyboard.down('Shift');
    await page.mouse.down();
    await page.mouse.move(start.x + 40, start.y + 10, { steps: 4 });
    await page.evaluate(() => testAssert(canvas._currentTransform?.actionPerformed, 'fixture did not start a drag'));
    if (kind === 'skew') await page.keyboard.up('Shift');
    await page.keyboard.press('Control+z');
    await page.waitForFunction(() => !editorMutationRunning);
    await page.evaluate(start => {
      testAssert(!canvas._currentTransform, 'undo kept live transform');
      testAssert(historyIndex === start.index, 'cancelling a drag consumed committed history');
      vinylObjects().forEach((o, i) => o.calcTransformMatrix().forEach((v, j) => testNear(v, start.matrices[i][j], 'undo drag transform')));
    }, start);
    await page.mouse.move(start.x + 80, start.y + 20, { steps: 3 });
    await page.mouse.up();
    interruptedDrags.push(await page.evaluate(start => {
      testAssert(historyIndex === start.index, 'mouse release committed cancelled drag');
      vinylObjects().forEach((o, i) => o.calcTransformMatrix().forEach((v, j) => testNear(v, start.matrices[i][j], 'cancelled drag resumed')));
      return testHelpers();
    }, start));
  }

  await page.evaluate(async () => {
    await testSetup({ skewX: 40 });
    activateDockPanel('propertiesPane');
  });
  await page.locator('#bringFront').click();
  await page.evaluate(() => testHelpers());
  await page.locator('#deleteLayer').click();
  await page.evaluate(() => { testAssert(testHelpers().outlines === 0, 'outline after delete'); testAssert(vinylObjects().length === 1, 'delete count'); });
  await page.locator('#undoBtn').click();
  await page.waitForFunction(() => !editorMutationRunning);
  await page.evaluate(() => { testHelpers(); testAssert(vinylObjects().length === 2, 'undo delete'); });
  await page.locator('#redoBtn').click();
  await page.waitForFunction(() => !editorMutationRunning);
  await page.evaluate(() => { testHelpers(); testAssert(vinylObjects().length === 1, 'redo delete'); });

  const lifecycle = await page.evaluate(async () => {
    for (let i = 0; i < 20; i++) {
      await testSetup({ skewX: i % 2 ? 35 : -35 }, i % 2 === 0);
      moveSelectedToEdge(true); testHelpers();
      await duplicateSelected(); testHelpers();
      deleteSelected(); testHelpers();
      const payload = editableProjectPayload('reload');
      await loadProjectPayload(payload, 'reload'); testHelpers();
    }
    await testSetup();
    const orphan = makeSelectionOutlineHelper(vinylObjects()[0]);
    canvas.add(orphan);
    canvas.discardActiveObject();
    syncSelectedShapeOutlines();
    testAssert(!canvas.getObjects().includes(orphan), 'legacy orphan not swept');
    testHelpers();
    // Delayed outline resolution must not recreate a deleted shape's rim.
    await testSetup();
    canvas.discardActiveObject();
    const owner = vinylObjects()[0];
    owner.kloudy.outline_path = null;
    owner.kloudy.outline_path_failed = false;
    const originalLoader = loadResourceOutlinePathForResolved;
    let finishOutline;
    try {
      loadResourceOutlinePathForResolved = () => new Promise(resolve => { finishOutline = resolve; });
      canvas.setActiveObject(owner); updateSelectionPanel();
      const pending = [...selectionOutlinePathPromises.values()];
      testAssert(pending.length > 0, 'outline fixture did not defer');
      deleteSelected();
      finishOutline('M -50 -50 L 50 -50 L 50 50 L -50 50 Z');
      await Promise.all(pending);
      testAssert(testHelpers().outlines === 0, 'late outline returned after delete');
    } finally {
      loadResourceOutlinePathForResolved = originalLoader;
    }
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => testShape(i % 2)) });
    canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel();
    moveSelectedToEdge(true); deleteSelected();
    testAssert(testHelpers().outlines === 0 && vinylObjects().length === 2999, 'dense delete');
    await testSetup({ skewX: 35 });
    moveSelectedToEdge(true); deleteSelected();
    currentProjectName = ''; loadedName = 'editor-regression';
    return testHelpers();
  });

  // Save through the UI and reopen the actual saved file after a page restart.
  await page.locator('#saveProject').click();
  await page.locator('#textPromptInput').fill(`editor-regression-${Date.now()}`);
  await page.locator('#textPromptConfirm').click();
  await page.waitForFunction(() => !projectSaveInProgress && Boolean(currentProjectName));
  const saved = await page.evaluate(async () => {
    const listing = await (await fetch(PROJECT_BROWSER_API)).json();
    return { listing, title: currentProjectName };
  });
  const entries = saved.listing.entries || saved.listing.projects || [];
  const entry = entries.find(e => e.title === saved.title || e.name === `${saved.title}.json`);
  if (!entry) throw new Error(`Saved project absent: ${JSON.stringify(saved)}`);
  const url = await page.evaluate(id => { const u = new URL(window.location.href); u.searchParams.set('project', id); return u.toString(); }, entry.id);
  await page.goto(url);
  await page.waitForFunction(() => Boolean(currentProjectName) && vinylObjects().length === 1);
  const reopened = await page.evaluate(() => ({
    layers: vinylObjects().length,
    outlines: canvas.getObjects().filter(o => o.kloudySelectionOutlineHelper).length,
  }));
  if (reopened.outlines !== 0) throw new Error('Outline returned after page restart');
  await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(d => d.close()));
  await page.setViewportSize({ width: 1100, height: 800 });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.screenshot({ path: 'editor-regression-compact.png' });
  if (errors.length) throw new Error(errors.join('\n'));
  return { matrixCases, cornerCases, pointerCases, cornerDrags, interruptedDrags, lifecycle, reopened, errors };
}
