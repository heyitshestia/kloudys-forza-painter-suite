async (page, options={}) => {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  await page.evaluate(async()=>{
    await loadPayload({shapes:Array.from({length:3000},(_,i)=>({type:1048677,color:[80,170,210,255],
      mask:i===2999,data:i===2999?[0,0,1.4,1.1,27,0,1]:[-270+i%60*9,185-Math.floor(i/60)*7.5,.07,.07,0,0,0]}))});
    applySavedGuideState(null);guideState.gridEnabled=false;guideState.snapGuides=false;
  });
  await page.locator('[data-tool-mode="select"]').click();await page.locator('#resizeFromCenter').uncheck();
  const session=await page.context().newCDPSession(page),results=[];
  try {
    for(const handle of ['tl','br','mr','mt']) {
      const p=await page.evaluate(handle=>{
        const o=vinylObjects().at(-1);selectObjects([o]);canvas.setViewportTransform([1.5,0,0,1.5,canvas.width/2,canvas.height/2]);
        o.setCoords();canvas.renderAll();const p=o.oCoords[handle],r=canvas.upperCanvasEl.getBoundingClientRect();
        window.hoverBefore=JSON.stringify(snapshotShapes());
        return {x:p.x+r.left,y:p.y+r.top};
      },handle);
      await page.keyboard.down('Alt');
      try {
        await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+12,p.y+9,{steps:5});
        const before=await page.evaluate(()=>canvas.getActiveObject().calcTransformMatrix().slice());
        // A separate real-device hover can arrive while CDP holds a synthetic
        // button, or after a missed mouse-up. It must not move a held transform.
        await session.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:p.x+(p.x<600?500:-500),y:p.y+(p.y<500?150:-150),buttons:0,modifiers:0});
        const drift=await page.evaluate(before=>Math.max(...canvas.getActiveObject().calcTransformMatrix().map((v,i)=>Math.abs(v-before[i]))),before);
        await page.mouse.move(p.x+22,p.y+15,{steps:5});await page.mouse.up();
        results.push({handle,unsolicitedHoverDrift:drift});
      } finally {await page.mouse.up();await page.keyboard.up('Alt');}
      await page.locator('#undoBtn').click();await page.waitForFunction(()=>JSON.stringify(snapshotShapes())===hoverBefore);
    }
  } finally {await session.detach();}
  fs.writeFileSync(path.join(output,'hover-isolation.json'),JSON.stringify(results,null,2));
  if(!options.recordBaseline&&results.some(r=>r.unsolicitedHoverDrift>1e-5))throw Error('Unpressed hover altered a resize: '+JSON.stringify(results));
  await page.evaluate(async()=>{await flushPendingAutosave();});
  await page.locator('#saveProjectAs').click();await page.locator('#textPromptInput').fill('Hover isolation qualification');
  await page.locator('#textPromptInput').press('Enter');await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
  return {results,layers:3000,injectedUnpressedMouseMove:true,baselineOnly:Boolean(options.recordBaseline)};
}
