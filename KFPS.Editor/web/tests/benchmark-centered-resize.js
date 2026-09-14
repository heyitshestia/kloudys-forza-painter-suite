async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  await page.setViewportSize({width:1600,height:1000});
  await page.evaluate(async () => {
    await loadPayload({shapes:Array.from({length:3000},(_,i)=>({type:i===2999?1048706:1048677,
      color:[100,170,210,160],data:i===2999?[0,0,1.4,1.1,27,0,0]:[-270+i%60*9,185-Math.floor(i/60)*7.5,.07,.07,0,0,0]}))});
    const image=document.createElement('canvas');image.width=5888;image.height=2816;
    const ctx=image.getContext('2d');ctx.fillStyle='#7d96a3';ctx.fillRect(0,0,image.width,image.height);
    await editorReference.loadOverlayImageFromUrl(image.toDataURL(),'center-performance.png');image.width=image.height=1;
    applySavedGuideState(null);guideState.gridEnabled=false;guideState.snapGuides=false;canvas.centeredScaling=false;
  });
  await page.locator('[data-tool-mode="select"]').click();
  const trace=await h.monitor(page,output);
  try {
    for(let i=0;i<(options.iterations||40);i++) {
      const handle=['br','mr','tl','mt'][i%4];
      const start=await page.evaluate(handle=>{
        const o=vinylObjects().at(-1);selectObjects([o]);
        canvas.setViewportTransform([1.5,0,0,1.5,canvas.width/2,canvas.height/2]);o.setCoords();canvas.renderAll();
        const p=o.oCoords[handle],r=canvas.upperCanvasEl.getBoundingClientRect();
        return {x:p.x+r.left,y:p.y+r.top,center:o.getCenterPoint(),shape:objectToShape(o)};
      },handle);
      await trace.run(`${i}/${handle}`,async()=>{
        await page.keyboard.down('Alt');
        try {
          await page.mouse.move(start.x,start.y);await page.mouse.down();
          for(const amount of [1,-.3,.7])await page.mouse.move(start.x+26*amount,start.y+19*amount,{steps:12});
          await page.mouse.up();
        } finally {await page.mouse.up();await page.keyboard.up('Alt');}
      });
      const drift=await page.evaluate(c=>{const a=canvas.getActiveObject().getCenterPoint();return Math.hypot(c.x-a.x,c.y-a.y);},start.center);
      if(drift>1e-5)throw Error('Center drift '+drift);
      await page.locator('#undoBtn').click();
      await page.waitForFunction(before=>JSON.stringify(objectToShape(vinylObjects().at(-1)))===JSON.stringify(before),start.shape);
    }
    await page.locator('#saveProjectAs').click();await page.locator('#textPromptInput').fill('Centered resize benchmark');
    await page.locator('#textPromptInput').press('Enter');await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
    return {iterations:trace.rows.length,rows:trace.rows,layers:3000,reference:[5888,2816],sharedBaselineAltGesture:true};
  } finally {await trace.close();}
}
