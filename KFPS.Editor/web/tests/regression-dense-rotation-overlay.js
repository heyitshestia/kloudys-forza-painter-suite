// A reused private transition fixture remains optional; default runs are self-contained.
async (page, options = {}) => {
  const handmade=options.project ? require(path.join(__dirname,'handmade-project-fixture.cjs')) : null;
  const initialProject=handmade ? await handmade.setup(page,output,options) : null;
  const targets=handmade ? await page.evaluate(()=>[27,30,36,39].map(slot=>({slot,id:vinylObjects()
    .filter(o=>o.kloudy.resource_family==='Primitives'&&o.kloudy.resource_index===slot)
    .sort((a,b)=>b.getScaledWidth()*b.getScaledHeight()-a.getScaledWidth()*a.getScaledHeight())[0]?.kloudy.editor_id}))) : null;
  let expectedTargetId=null;
  if (!handmade && !options.existingFixture) await page.evaluate(async () => {
    const shapes = Array.from({length:2997},(_,i)=>({type:editorCatalog.resourceToTypeCode('Primitives',1),
      color:[80,140,190,255],data:[i%60*24-720,Math.floor(i/60)*24-600,.12,.12,0,0,0]}));
    for(const [index,slot] of [30,36,39].entries())shapes.push({type:editorCatalog.resourceToTypeCode('Primitives',slot),
      editor_id:`target-${slot}`,shape_name:`Transition target ${slot}`,color:[215,70,125,255],
      data:[(index-1)*300,0,2,2,0,0,0]});
    await loadPayload({shapes});
    currentProjectName='Dense rotation regression';
    const source=document.createElement('canvas');source.width=6000;source.height=4000;
    const context=source.getContext('2d');context.fillStyle='#739298';context.fillRect(0,0,6000,4000);
    await editorReference.loadOverlayImageFromUrl(source.toDataURL(),'dense-rotation-24MP.png');
    source.width=source.height=1;
    await flushPendingAutosave();
  });
  const expectedCount=initialProject?.layers || 3000;
  await page.waitForFunction(count => vinylObjects().length === count && editorReference.image,expectedCount);
  await page.evaluate(() => {
    window.rotationRenderer = typeof editorRenderer === 'undefined'
      ? {get active(){return hybridRenderActive;}} : editorRenderer;
  });
  const expectMissing = process.env.KFPS_EXPECT_MISSING_RING === '1';
  const evidence = [];
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const geometry = () => page.evaluate(expectedTargetId => {
    const target = canvas.getActiveObject();
    if (expectedTargetId ? target?.kloudy?.editor_id !== expectedTargetId : !target?.kloudy?.editor_id.startsWith('target-')) throw new Error('Wrong rotation target');
    const bounds = canvas.upperCanvasEl.getBoundingClientRect();
    const center = fabric.util.transformPoint(target.getCenterPoint(), canvas.viewportTransform);
    const ring = rotationNotchMetrics(target);
    return { center: { x: bounds.left + center.x, y: bounds.top + center.y },
      handle: { x: bounds.left + target.oCoords.mtr.x, y: bounds.top + target.oCoords.mtr.y },
      radius: ring.radius * canvas.getZoom(), angle: target.angle, id: target.kloudy.editor_id };
  },expectedTargetId);
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
      snapHelpers: snapOverlayObjects.length, active: rotationRenderer.active,
      lowerHidden: canvas.lowerCanvasEl.style.visibility === 'hidden', angle: target.angle,
      layerCount: vinylObjects().length, referenceMode: overlayLayerMode,
      focus: document.hasFocus(), transform: canvas._currentTransform?.action };
  });
  for (const mode of ['below', 'above']) for (const slot of handmade ? targets.map(t=>t.slot) : [30,36,39]) {
    await page.locator('[data-panel="overlayPane"]').click();
    await page.locator('#overlayLayerMode').selectOption(mode);
    const original=handmade ? await handmade.snapshot(page) : null;
    if(handmade) {
      expectedTargetId=targets.find(t=>t.slot===slot).id;
      await handmade.selectId(page,expectedTargetId);await page.locator('#bringFront').click();
      await handmade.frameSelection(page);
      for(let i=0;i<12;i++) {
        const g=await geometry(),b=await page.locator('.upper-canvas').boundingBox();
        if(g.center.x-g.radius>b.x+15&&g.center.x+g.radius<b.x+b.width-15&&g.center.y-g.radius>b.y+15&&g.center.y+g.radius<b.y+b.height-15)break;
        await page.mouse.move(g.center.x,g.center.y);await page.mouse.wheel(0,150);await page.waitForTimeout(60);
      }
    } else {
      await page.locator('#layerSearch').fill(`Transition target ${slot}`);
      await page.locator('.layerRow').filter({ hasText: `Transition target ${slot}` }).click();
      await page.locator('#fitView').click();
    }
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
    await page.waitForFunction(() => snapOverlayObjects.length === 0 && !rotationRenderer.active);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const cleared = await page.evaluate(() => {
      const pixels = canvas.contextTop.getImageData(0, 0, canvas.contextTop.canvas.width, canvas.contextTop.canvas.height).data;
      let ink = 0;
      for (let i = 3; i < pixels.length; i += 4) if (pixels[i]) ink++;
      return ink;
    });
    if (cleared) throw new Error('Rotation overlay left stale pixels after release: ' + cleared);
    if(handmade) {
      for(let i=0;i<3&&await handmade.snapshot(page)!==original;i++) {
        await page.locator('#undoBtn').click();await page.waitForFunction(()=>!editorCommands.busy);
      }
      if(await handmade.snapshot(page)!==original)throw Error('Rotation ring workflow changed original artwork or order after undo');
    }
  }
  let overlayFault=null;
  if(options.overlayFaultCheck) {
    const before=handmade ? await handmade.snapshot(page) : null;
    await page.evaluate(()=>{
      canvas.renderAll();
      window.__overlayFaultPixels=canvas.contextContainer.getImageData(0,0,canvas.lowerCanvasEl.width,canvas.lowerCanvasEl.height).data;
      const draw=canvas.drawControls;
      canvas.drawControls=function(context) {
        if(context===this.contextTop&&editorRenderer.active&&this.lowerCanvasEl.style.visibility==='hidden') {
          this.drawControls=draw;
          throw new Error('Controlled interaction overlay failure');
        }
        return draw.call(this,context);
      };
      if(!editorRenderer.beginHybridRender('overlay fault qualification'))throw Error('GPU preview was unavailable before fault injection');
    });
    await page.waitForFunction(()=>editorRenderer.disabledReason==='Interaction overlay unavailable'&&!editorRenderer.active);
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    overlayFault=await page.evaluate(()=>{
      const actual=canvas.contextContainer.getImageData(0,0,canvas.lowerCanvasEl.width,canvas.lowerCanvasEl.height).data;
      const expected=window.__overlayFaultPixels;
      const result={lowerVisible:canvas.lowerCanvasEl.style.visibility!=='hidden',exactFallbackPixels:actual.length===expected.length&&actual.every((value,i)=>value===expected[i]),layers:vinylObjects().length};
      delete window.__overlayFaultPixels;
      return result;
    });
    if(!overlayFault.lowerVisible||!overlayFault.exactFallbackPixels||overlayFault.layers!==expectedCount)throw Error('Overlay fault did not restore the complete normal frame: '+JSON.stringify(overlayFault));
    if(handmade&&await handmade.snapshot(page)!==before)throw Error('Overlay fault changed artwork');
  }
  await page.locator('#layerSearch').fill('');
  await page.locator('#saveProject').click();
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(() => flushPendingAutosave());
  fs.writeFileSync(path.join(output, 'rotation-overlay-evidence.json'), JSON.stringify(evidence, null, 2));
  if (errors.length) throw new Error(errors.join('\n'));
  return { expectMissing, initialProject, loaded: expectedCount, cases: evidence.length, evidence, overlayFault };
}
