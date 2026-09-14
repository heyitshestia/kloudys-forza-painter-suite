async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const check = (value, message) => { if (!value) throw Error(message); };
  const handles = ['tl', 'tr', 'bl', 'br', 'ml', 'mr', 'mt', 'mb'];
  const modes = [{ on: false, alt: false }, { on: true, alt: false },
    { on: false, alt: true }, { on: true, alt: true }];
  const variants = options.variants || ['rectangle', 'quarter', 'ellipse-skew-mirror', 'mask', 'group'];
  const results = [], trace = await h.monitor(page, output);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.evaluate(()=>{
    window.centerEvents=[];
    const describe=o=>o&&({id:o.kloudy?.editor_id,owner:o.kloudyMaskOwner?.kloudy?.editor_id,
      center:o.getCenterPoint(),matrix:o.calcOwnMatrix().slice(),origin:[o.originX,o.originY],width:o.width,height:o.height});
    window.centerObserver=event=>{
      if(centerEvents.length>=30)return;
      const t=event.transform||canvas._currentTransform;
      centerEvents.push({target:describe(t?.target||event.target),active:describe(canvas.getActiveObject()),
        alt:event.e?.altKey,ctrl:event.e?.ctrlKey,buttons:event.e?.buttons,clientX:event.e?.clientX,clientY:event.e?.clientY,
        corner:t?.corner,action:t?.action,ex:t?.ex,ey:t?.ey,
        gesture:t?.kloudyCornerGesture||t?.kloudySideResize});
    };
    canvas.on('before:transform',centerObserver);canvas.on('object:scaling',centerObserver);
  });
  async function setup(variant) {
    await page.evaluate(async variant => {
      const group = variant === 'group', count = group ? 48 : 1;
      await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
        type: i < 3000 - count ? 1048677 : variant === 'quarter' ? 1048706 : variant.includes('ellipse') ? 1048678 : 1048677,
        color: [90, 180, 210, i >= 3000 - count ? 160 : 255], mask: variant === 'mask' && i === 2999,
        data: i < 3000 - count ? [-270 + i % 60 * 9, 185 - Math.floor(i / 60) * 7.5, .07, .07, 0, 0, 0]
          : [group ? (i - 2952) % 8 * 45 - 157.5 : 0, group ? Math.floor((i - 2952) / 8) * 38 - 95 : 0,
            group ? .35 : 1.4, group ? .35 : 1.1, variant === 'rectangle' ? 0 : 27, 0, 0],
        editor_id: `center-${i}`, ...(group && i >= 3000 - count ? { editor_group_id: 'center-group', editor_group_name: 'Resize group' } : {}),
      })) });
      if (variant.includes('skew')) {
        vinylObjects().at(-1).set({ skewX: 24, skewY: -8, flipX: true, flipY: true });
        vinylObjects().at(-1).setCoords();
        // Normalize through the real import contract before comparing a replay
        // against undo. Forza stores one shear, not Fabric's two-shear basis.
        await loadPayload({ shapes: snapshotShapes() });
      }
      if (!editorReference.image) {
        const image = document.createElement('canvas'); image.width = 5888; image.height = 2816;
        const ctx = image.getContext('2d'); ctx.fillStyle = '#7d96a3'; ctx.fillRect(0, 0, image.width, image.height);
        await editorReference.loadOverlayImageFromUrl(image.toDataURL(), 'centered-reference.png'); image.width = image.height = 1;
      }
      applySavedGuideState(null); guideState.gridEnabled = false; guideState.snapCtrlOnly = true;
      window.centerTestCount = count;
      window.centerOriginal = JSON.stringify(snapshotShapes());
      window.centerUntouched = JSON.stringify(snapshotShapes().slice(0, -count));
    }, variant);
    await page.locator('[data-tool-mode="select"]').click();
  }
  async function start(handle, on) {
    await page.evaluate(() => {
      selectObjects(vinylObjects().slice(-centerTestCount));
      canvas.setViewportTransform([1.5, 0, 0, 1.5, canvas.width / 2, canvas.height / 2]);
      canvas.getActiveObject().setCoords(); styleActiveTransformControls(); canvas.renderAll();
    });
    await page.locator('#resizeFromCenter').setChecked(on);
    return page.evaluate(handle => {
      const o = canvas.getActiveObject(), c = o.getCenterPoint(), p = o.oCoords[handle];
      const rect = canvas.upperCanvasEl.getBoundingClientRect();
      const sx = (handle.includes('r') ? 1 : handle.includes('l') ? -1 : 0) * (o.flipX ? -1 : 1);
      const sy = (handle.includes('b') ? 1 : handle.includes('t') ? -1 : 0) * (o.flipY ? -1 : 1);
      window.centerAnchor = new fabric.Point(-sx * o.width / 2, -sy * o.height / 2);
      window.centerFixed = fabric.util.transformPoint(centerAnchor, o.calcTransformMatrix());
      window.centerBefore = JSON.stringify(snapshotShapes());
      window.centerBeforeTransform = o.calcTransformMatrix().slice();
      window.centerGesture = { center: c, maxDrift: 0, oppositeDrift: 0, samples: 0 };
      window.centerEvents=[];
      return { x: p.x + rect.left, y: p.y + rect.top,
        dx: (p.x - (c.x * 1.5 + canvas.width / 2)) * .25,
        dy: (p.y - (c.y * 1.5 + canvas.height / 2)) * .25 };
    }, handle);
  }
  async function sample(centered) {
    const result=await page.evaluate(centered => {
      const o = canvas.getActiveObject(), c = o.getCenterPoint(), m = centerGesture;
      const fixed = fabric.util.transformPoint(centerAnchor, o.calcTransformMatrix());
      const drift = Math.hypot(c.x - m.center.x, c.y - m.center.y);
      const opposite = Math.hypot(fixed.x - centerFixed.x, fixed.y - centerFixed.y);
      m.maxDrift = Math.max(m.maxDrift, drift); m.oppositeDrift = Math.max(m.oppositeDrift, opposite); m.samples++;
      if (!o.calcTransformMatrix().every(Number.isFinite)) throw Error('Invalid geometry');
      return {failed:(centered?drift:opposite)>1e-5,drift,opposite,centered,events:window.centerEvents,
        active:interactiveVinylTarget(o)?.kloudy?objectToShape(interactiveVinylTarget(o)):{group:true,matrix:o.calcTransformMatrix()},
        before:JSON.parse(centerBefore).slice(-centerTestCount)};
    }, centered);
    if(result.failed) {
      fs.writeFileSync(path.join(output,'center-anchor-failure.json'),JSON.stringify(result,null,2));
      throw Error(`Anchor drift: center=${result.drift}, opposite=${result.opposite}`);
    }
  }
  async function undoRedo(label) {
    const metrics = await page.evaluate(() => {
      const o = canvas.getActiveObject();
      if (o.calcTransformMatrix().every((v, i) => Math.abs(v - centerBeforeTransform[i]) < 1e-8)) throw Error('Gesture did not resize');
      if (JSON.stringify(snapshotShapes().slice(0, -centerTestCount)) !== centerUntouched) throw Error('Unrelated shapes changed');
      window.centerAfter = JSON.stringify(snapshotShapes());
      return centerGesture;
    });
    await page.locator('#undoBtn').click();
    await page.waitForFunction(() => !editorCommands.busy && JSON.stringify(snapshotShapes()) === centerBefore);
    await page.locator('#redoBtn').click();
    await page.waitForFunction(() => !editorCommands.busy && JSON.stringify(snapshotShapes()) === centerAfter);
    await page.locator('#undoBtn').click();
    await page.waitForFunction(() => !editorCommands.busy && JSON.stringify(snapshotShapes()) === centerBefore);
    results.push({ label, ...metrics, exactUndoRedo: true });
    fs.writeFileSync(path.join(output, 'centered-resize.json'), JSON.stringify(results, null, 2));
  }
  try {
    for (const variant of variants) {
      await setup(variant);
      for (const [index, mode] of modes.entries()) for (const handle of handles) {
        const label = `${variant}/${handle}/on=${mode.on}/alt=${mode.alt}`;
        await trace.run(label, async () => {
          const p = await start(handle, mode.on), centered = mode.on !== mode.alt;
          const steps = [1, 6, 18, 4][index];
          if (mode.alt) await page.keyboard.down('Alt');
          try {
            await page.mouse.move(p.x, p.y); await page.mouse.down();
            for (const amount of [.4, 1, -.2, .7]) {
              await page.mouse.move(p.x + p.dx * amount, p.y + p.dy * amount, { steps });
              await sample(centered);
            }
            await page.mouse.up(); await sample(centered);
          } finally { await page.mouse.up(); await page.keyboard.up('Alt'); }
          await undoRedo(label);
        });
      }
    }
    await setup('quarter');
    for (const handle of options.skipMidDrag ? [] : handles) for (const initiallyOn of [false, true]) {
      const label = `mid-drag/${handle}/${initiallyOn}`;
      await trace.run(label, async () => {
        const p = await start(handle, initiallyOn);
        try {
          await page.mouse.move(p.x, p.y); await page.mouse.down();
          await page.mouse.move(p.x + p.dx * .3, p.y + p.dy * .3, { steps: 5 });
          await sample(initiallyOn);
          for (const [alt, amount] of [[true, .65], [false, 1]]) {
            await page.evaluate(() => {
              const o = canvas.getActiveObject(); centerGesture.center = o.getCenterPoint();
              centerFixed = fabric.util.transformPoint(centerAnchor, o.calcTransformMatrix());
            });
            await page.keyboard[alt ? 'down' : 'up']('Alt');
            await page.mouse.move(p.x + p.dx * amount, p.y + p.dy * amount, { steps: 9 });
            await sample(initiallyOn !== alt);
          }
          await page.mouse.up();
        } finally { await page.mouse.up(); await page.keyboard.up('Alt'); }
        await undoRedo(label);
      });
    }
    // Place a real guide just beyond a contact measured from an unsnapped pointer
    // resize. Replaying the same pointer with Ctrl must reach it without translation.
    for (const variant of options.snapVariants || ['quarter', 'ellipse-skew-mirror', 'mask']) {
      await setup(variant);
      for (const handle of handles) {
        const label = `snap/${variant}/${handle}`;
        await trace.run(label, async () => {
          const p = await start(handle, true);
          await h.drag(page, p, { x: p.x + p.dx, y: p.y + p.dy });
          const contact = await page.evaluate(handle => {
            const o = canvas.getActiveObject(), kind = ({ml:'left',mr:'right',mt:'top',mb:'bottom'})[handle] || handle;
            const point = objectCornerCoords(o)[kind], center = o.getCenterPoint();
            const dx = point.x - center.x, dy = point.y - center.y, length = Math.hypot(dx, dy);
            return { point, normal: { x: dx / length, y: dy / length }, kind };
          }, handle);
          await page.locator('#undoBtn').click();
          await page.waitForFunction(() => JSON.stringify(snapshotShapes()) === centerBefore);
          const q = await start(handle, true);
          await page.evaluate(({ point, normal }) => {
            const d = { x: point.x + normal.x * 2, y: point.y + normal.y * 2 };
            guideState.snapGuides = true;
            guideState.guides = [{id:'center-contact',x1:d.x-normal.y*800,y1:d.y+normal.x*800,
              x2:d.x+normal.y*800,y2:d.y-normal.x*800,constraint:'free'}]; renderGuideObjects();
          }, contact);
          await h.drag(page, q, { x: q.x + q.dx, y: q.y + q.dy }, ['Control']);
          await sample(true);
          const distance = await page.evaluate(kind => {
            const point = objectCornerCoords(canvas.getActiveObject())[kind];
            const line = guideState.guides[0], dx = line.x2 - line.x1, dy = line.y2 - line.y1;
            return Math.abs(dx * (point.y-line.y1) - dy * (point.x-line.x1)) / Math.hypot(dx,dy);
          }, contact.kind);
          if (distance >= 1e-5) fs.writeFileSync(path.join(output, 'centered-snap-failure.json'), JSON.stringify({label,p,q,contact,distance,
            actual:await page.evaluate(()=>({shape:objectToShape(canvas.getActiveObject()),coords:objectCornerCoords(canvas.getActiveObject()),guide:guideState.guides}))},null,2));
          check(distance < 1e-5, `${label}: contact missed guide by ${distance}`);
          await undoRedo(label);
          await page.evaluate(() => { guideState.guides=[]; renderGuideObjects(); });
        });
      }
    }
    await page.evaluate(async () => {
      await flushPendingAutosave();
      if (JSON.stringify((await readAutosavePayload()).shapes) !== JSON.stringify(snapshotShapes())) throw Error('Recovery differs');
    });
    await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill('Centered resize qualification');
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    await page.locator('#resizeFromCenter').check();
    await page.waitForFunction(async () => (await (await fetch('/api/fabric-editor/preferences')).json()).settings.kloudyFabricCenteredResize === '1');
    await page.screenshot({ path: path.join(output, 'centered-resize-en.png') });
    check(trace.rows.every(row => row.after.visible >= 2700), 'Dense visibility lost');
    return { cases: results.length, results, rows: trace.rows, layers: 3000, reference: [5888,2816], exactUndoRedo: true };
  } finally {
    await page.evaluate(()=>{canvas.off('before:transform',centerObserver);canvas.off('object:scaling',centerObserver);});
    await trace.close();
  }
}
