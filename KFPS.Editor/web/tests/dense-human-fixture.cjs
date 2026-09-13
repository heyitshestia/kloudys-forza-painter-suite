"use strict";
const fs = require('node:fs');
const path = require('node:path');

async function fileInput(page, selector, filename) {
  const session = await page.context().newCDPSession(page);
  try {
    const { root } = await session.send('DOM.getDocument', { depth: 0 });
    const { nodeId } = await session.send('DOM.querySelector', { nodeId: root.nodeId, selector });
    if (!nodeId) throw Error(`Missing file input: ${selector}`);
    await session.send('DOM.setFileInputFiles', { nodeId, files: [filename] });
  } finally { await session.detach(); }
}

async function type(page, selector, value) {
  const input = page.locator(selector);
  await input.click();
  await input.press('Control+A');
  await input.pressSequentially(String(value), { delay: 12 });
}

async function setup(page, output, options = {}) {
  if (options.project) return require('./handmade-project-fixture.cjs').setupDerived(page, output, options);
  const count = Number(options.layers || 2400);
  if (!Number.isInteger(count) || count < 2000 || count > 2950) throw Error('Dense fixture requires 2000-2950 layers with insertion headroom');
  const shapes = Array.from({ length: count - 50 }, (_, i) => ({
    type: [1048677,1048678,1048706,1048712,1048715][i % 5],
    color: [40 + i % 150, 90 + i % 120, 170, i % 9 ? 255 : 160],
    data: [-690 + i % 60 * 23, 440 - Math.floor(i / 60) * 23, .12, .16, i % 4 * 15, 0, 0],
    editor_id: `dense-background-${i}`, shape_name: `Background ${i}`,
  }));
  for (let i = 0; i < 48; i++) shapes.push({
    type: i % 2 ? 1048678 : 1048677, color: [210,80,130,255],
    data: [-190 + i % 12 * 34, 100 - Math.floor(i / 12) * 35, .22,.22,0,0,0],
    editor_id: `dense-batch-${i}`, shape_name: `Batch member ${i}`,
    editor_group_id: 'dense-batch', editor_group_name: 'Dense batch',
  });
  shapes.push({type:1048706,color:[245,180,60,255],data:[-180,-190,1.5,1.5,0,0,0],editor_id:'dense-target',shape_name:'Human target'});
  shapes.push({type:1048678,color:[90,205,195,255],data:[210,-190,1.4,1.4,0,0,0],editor_id:'dense-other',shape_name:'Human alternate'});
  const filename = path.join(output, 'dense-input.json');
  fs.writeFileSync(filename, JSON.stringify({shapes}));
  await fileInput(page, '#jsonInput', filename);
  await page.waitForFunction(count => vinylObjects().length === count && !recoveryRestoreDepth, count);
  if (options.reference) {
    await page.locator('[data-tool-mode="overlay"]').click();
    await fileInput(page, '#overlayInput', options.reference);
    await page.waitForFunction(() => editorReference.image && !recoveryRestoreDepth);
    await page.locator('#overlayOpacity').focus(); await page.keyboard.press('Home');
    const opacity=Number(options.opacity ?? 60);
    if(!Number.isInteger(opacity)||opacity<0||opacity>100)throw Error('Invalid reference opacity');
    for (let i = 0; i < opacity; i++) await page.keyboard.press('ArrowRight');
  }
  await page.locator('[data-tool-mode="select"]').click();
  await page.locator('#fitView').click();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const view = await scene(page);
  if (view.visible < count * .8) throw Error('Dense fixture was not substantially visible: ' + JSON.stringify(view));
  return { ...view, setup: 'Synthetic JSON imported through real file-input workflow; optional native reference file input. Actions use pointer/keyboard, assertions read state.' };
}

async function scene(page) {
  return page.evaluate(() => {
    const objects = vinylObjects(), matrix = canvas.viewportTransform;
    let visible = 0;
    for (const object of objects) {
      if (!object.visible) continue;
      const box = KfpsFabricAdapter.sceneBounds(object);
      const a = fabric.util.transformPoint(new fabric.Point(box.left, box.top), matrix);
      const b = fabric.util.transformPoint(new fabric.Point(box.left + box.width, box.top + box.height), matrix);
      if (b.x >= 0 && b.y >= 0 && a.x <= canvas.width && a.y <= canvas.height) visible++;
    }
    return { layers: objects.length, visible, selected: selectedVinylObjects().length,
      cachePixels: objects.reduce((sum,o)=>sum+(o._cacheCanvas?.width||0)*(o._cacheCanvas?.height||0),0),
      reference: editorReference.image ? [editorReference.image.width,editorReference.image.height] : null,
      referenceOrder: overlayLayerMode, referenceOpacity: Number(document.getElementById('overlayOpacity').value),
      zoom: canvas.getZoom(), hidden: document.hidden };
  });
}

async function select(page, name, group = false) {
  await type(page, '#layerSearch', name);
  await page.locator(group ? '.layerGroupRow' : '.layerRow').filter({ hasText: name }).first().click();
  await page.waitForFunction(() => selectedVinylObjects().length > 0);
}

async function snapshot(page) { return page.evaluate(() => JSON.stringify(snapshotShapes())); }

async function geometry(page) {
  return page.evaluate(() => {
    const object=canvas.getActiveObject();
    const members=object?.kloudy?[object]:(object?.getObjects?.()||[]).filter(o=>o.kloudy&&!o.kloudy.locked&&o.visible);
    if(!members.length)throw Error('Gesture target is not a selected vinyl or selection');
    object.setCoords();
    const rect=canvas.upperCanvasEl.getBoundingClientRect();
    const point=p=>({x:p.x+rect.left,y:p.y+rect.top});
    const scenePoint=p=>point(fabric.util.transformPoint(p,canvas.viewportTransform));
    const painted=members[0],matrix=painted.calcTransformMatrix();
    let grab=null;
    for(const x of [0,-.15,.15,-.3,.3,-.42,.42]) {
      for(const y of [0,-.15,.15,-.3,.3,-.42,.42]) {
        const p=fabric.util.transformPoint(new fabric.Point(painted.width*x,painted.height*y),matrix);
        if(KfpsFabricAdapter.visiblePixelAt(canvas,painted,p)){grab=scenePoint(p);break;}
      }
      if(grab)break;
    }
    if(!grab) {
      const normal=[], retry=[];
      for(const x of [0,-.15,.15,-.3,.3,-.42,.42])for(const y of [0,-.15,.15,-.3,.3,-.42,.42]) {
        const p=fabric.util.transformPoint(new fabric.Point(painted.width*x,painted.height*y),matrix);
        const q=fabric.util.transformPoint(p,canvas.viewportTransform);
        if(!canvas.isTargetTransparent(painted,q.x,q.y))normal.push([x,y]);
        if(KfpsFabricAdapter.visiblePixelAt(canvas,painted,p))retry.push([x,y]);
      }
      const failure={shape:objectToShape(painted),matrix,bounds:KfpsFabricAdapter.sceneBounds(painted),
        viewport:canvas.viewportTransform,preview:editorRenderer.active,normal,retry,pointerTrace:window.handmadePointerTrace||null};
      throw Error('Target has no hittable painted point on sampling grid: '+JSON.stringify(failure));
    }
    const handles=Object.fromEntries(Object.entries(object.oCoords).map(([name,p])=>[name,point(p)]));
    return {grab,center:scenePoint(object.getCenterPoint()),handles,shape:object.kloudy?objectToShape(object):null,members:members.length,zoom:canvas.getZoom(),
      left:object.left,top:object.top,angle:object.angle,scaleX:object.scaleX,scaleY:object.scaleY,skewX:object.skewX,skewY:object.skewY};
  });
}

async function drag(page,from,to,modifiers=[]) {
  for(const modifier of modifiers)await page.keyboard.down(modifier);
  try {
    await page.mouse.move(from.x,from.y);await page.mouse.down();
    await page.mouse.move(to.x,to.y,{steps:12});await page.mouse.up();
  } finally {await page.mouse.up();for(const modifier of modifiers.reverse())await page.keyboard.up(modifier);}
}

async function undo(page, before) {
  await page.locator('#undoBtn').click();
  await page.waitForFunction(() => !editorCommands.busy);
  const after = await snapshot(page);
  if (after !== before) {
    const expected = JSON.parse(before), actual = JSON.parse(after);
    const differences = actual.map((shape,index) => ({ index, expected: expected[index], actual: shape }))
      .filter(item => JSON.stringify(item.expected) !== JSON.stringify(item.actual));
    fs.writeFileSync(path.join(process.cwd(), 'undo-failure.json'), JSON.stringify({ expectedCount: expected.length,
      actualCount: actual.length, differenceCount: differences.length, differences: differences.slice(0,30) }, null, 2));
    throw Error('Pointer/button operation did not undo to exact dense state: ' + differences.length + ' differing shapes');
  }
}

async function monitor(page, output) {
  const rows = [];
  await page.evaluate(() => {
    const state = window.denseHumanMeasure = { current: null, stopped: false };
    state.observer = new PerformanceObserver(list => {
      if (state.current) state.current.tasks.push(...list.getEntries().map(e => e.duration));
    });
    state.observer.observe({ entryTypes: ['longtask'] });
    let last = 0;
    const frame = now => {
      if (state.current && last && state.current.frames.length < 50000) state.current.frames.push(now-last);
      last = state.current ? now : 0;
      if (!state.stopped) state.frame = requestAnimationFrame(frame);
    };
    state.frame = requestAnimationFrame(frame);
  });
  return {
    rows,
    async run(name, action) {
      const before = await scene(page);
      await page.evaluate(() => { denseHumanMeasure.current = { frames: [], tasks: [], at: performance.now() }; });
      let error = null;
      try { await action(); } catch (caught) { error = caught; }
      // Include the delayed normal-canvas redraw, not just the GPU gesture.
      await page.waitForTimeout(350);
      const metrics = await page.evaluate(() => {
        const m = denseHumanMeasure.current; denseHumanMeasure.current = null;
        const frames = m.frames.sort((a,b)=>a-b);
        return { ms: performance.now()-m.at, frames: frames.length, p95: frames[Math.floor(frames.length*.95)] || 0,
          max: Math.max(0,...frames), gaps100: frames.filter(ms=>ms>=100).length,
          gaps500: frames.filter(ms=>ms>=500).length, longTasks: m.tasks };
      });
      rows.push({name,before,after:await scene(page),...metrics,passed:!error,error:error ? String(error.stack || error) : null});
      fs.writeFileSync(path.join(output,'dense-human-progress.json'),JSON.stringify(rows,null,2));
      if (error) throw error;
    },
    async close() {
      await page.evaluate(() => { denseHumanMeasure.stopped=true; cancelAnimationFrame(denseHumanMeasure.frame); denseHumanMeasure.observer.disconnect(); });
    },
  };
}

module.exports = {fileInput,type,setup,scene,select,snapshot,geometry,drag,undo,monitor};
