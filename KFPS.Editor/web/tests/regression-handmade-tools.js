async (page, options = {}) => {
  const h=require(path.join(__dirname,'handmade-project-fixture.cjs'));
  page.setDefaultTimeout(30000);
  const initial=await h.setup(page,output,options),original=await h.snapshot(page);
  const id=await page.evaluate(()=>vinylObjects().filter(o=>o.kloudy.resource_family==='Primitives'&&o.kloudy.resource_index===27)
    .sort((a,b)=>b.getScaledWidth()*b.getScaledHeight()-a.getScaledWidth()*a.getScaledHeight())[0].kloudy.editor_id);
  await h.selectId(page,id);await page.locator('#bringFront').click();await h.frameSelection(page);
  const exposed=await h.snapshot(page),trace=await h.monitor(page,output),checks=[];
  const idle=()=>page.waitForFunction(()=>!editorCommands.busy);
  const restore=async expected=>{
    for(let i=0;i<8&&await h.snapshot(page)!==expected;i++){await page.locator('#undoBtn').click();await idle();}
    h.check(await h.snapshot(page)===expected,'Tool workflow did not restore exact artwork');
  };
  try {
    for(const axis of ['x','y'])for(const speed of Object.keys(h.speeds)) {
      await h.selectId(page,id);await page.locator('.upper-canvas').focus();const before=await h.geometry(page);
      await trace.run(`axis/${axis}/${speed}`,async()=>{
        await h.motion(page,before.grab,{x:before.grab.x+23,y:before.grab.y+17},speed,[axis]);
        const after=await h.geometry(page);
        await h.expectTranslation(page,before,after,axis==='x'?23:0,axis==='y'?17:0);
        h.check(await page.evaluate(()=>dragAxisLock===null),'Axis lock survived key release');
      });
      await h.undo(page,exposed);checks.push(`axis/${axis}/${speed}`);
    }
    for(const mode of ['dominant','average']) {
      await h.selectId(page,id);await page.locator('#overlaySampleMode').selectOption(mode);
      const expected=await page.evaluate(()=>{
        const o=selectedVinylObjects()[0],c=editorReference.dominantOverlayColorForObject(o);
        return c&&[...c.slice(0,3),Math.round(o.opacity*255)];
      });
      h.check(expected,'Actual reference does not cover selected handmade shape');
      await trace.run(`reference-sample/${mode}`,async()=>{
        await page.locator('#sampleOverlayColor').click();
        h.check(JSON.stringify((await h.geometry(page)).shape.color)===JSON.stringify(expected),'Sampling button did not apply the requested mode or preserve alpha');
      });
      await restore(exposed);checks.push(`reference-sample/${mode}`);
    }
    await h.selectId(page,id);
    await page.locator('#autoOverlayColor').check();
    for(const speed of Object.keys(h.speeds))await trace.run(`live-reference/${speed}`,async()=>{
      const before=await h.geometry(page);
      await h.motion(page,before.grab,{x:before.grab.x+21,y:before.grab.y-15},speed);
      const after=await h.geometry(page);await h.expectTranslation(page,before,after,21,-15);
      h.check(await page.evaluate(()=>{
        const o=selectedVinylObjects()[0],c=editorReference.dominantOverlayColorForObject(o);
        return c&&objectToShape(o).color.slice(0,3).every((v,i)=>v===c[i]);
      }),'Live reference color was stale after movement');
    });
    await page.locator('#autoOverlayColor').uncheck();await restore(exposed);
    const point=await h.geometry(page);
    const expectedPixel=await page.evaluate(({x,y})=>{
      const r=canvas.upperCanvasEl.getBoundingClientRect();
      const p=fabric.util.transformPoint({x:x-r.left,y:y-r.top},fabric.util.invertTransform(canvas.viewportTransform));
      return editorReference.overlayColorAtCanvasPoint(p.x,p.y);
    },{x:Math.round(point.grab.x),y:Math.round(point.grab.y)});
    h.check(expectedPixel,'No reference pixel for eyedropper probe');
    await page.locator('#colorEyedropper').click();
    await page.mouse.click(Math.round(point.grab.x),Math.round(point.grab.y));
    h.check(await page.evaluate(id=>selectedVinylObjects()[0]?.kloudy.editor_id===id,id),'Eyedropper changed selection');
    h.check(JSON.stringify((await h.geometry(page)).shape.color)===JSON.stringify(expectedPixel),'Eyedropper did not sample the original above-reference pixel');
    await page.locator('#colorEyedropper').click();await restore(exposed);
    await restore(original);
    await page.locator('#fitView').click();
    const box=await page.locator('.upper-canvas').boundingBox();
    const from={x:Math.round(box.x+box.width*.4),y:Math.round(box.y+box.height*.4)};
    const to={x:Math.round(box.x+box.width*.64),y:Math.round(box.y+box.height*.7)};
    let expectedIds=null;
    for(const visible of [true,false])for(const speed of Object.keys(h.speeds))for(const invert of [false,true]){
      await page.locator('#invertBoxSelect').uncheck();
      if(await page.locator('#clearLayerSelection').isEnabled())await page.locator('#clearLayerSelection').click();
      await page.locator('#boxVisibleOnly').setChecked(visible);
      await page.locator('#invertBoxSelect').setChecked(invert);
      await page.locator('.upper-canvas').focus();
      await trace.run(`marquee/${visible}/${speed}/${invert}`,async()=>{
        await h.motion(page,from,to,speed,['v']);
        h.check(await page.evaluate(()=>!vBoxSelectActive&&!canvas.skipTargetFind),'V box selection remained captured after key release');
      });
      const selected=await page.evaluate(()=>selectedVinylObjects().map(o=>o.kloudy.editor_id).sort());
      if(!expectedIds){h.check(selected.length>2&&selected.length<initial.layers,'Marquee fixture did not select a useful partial set');expectedIds=selected;}
      const expected=invert?JSON.parse(original).map(s=>s.editor_id).filter(id=>!expectedIds.includes(id)).sort():expectedIds;
      h.check(JSON.stringify(selected)===JSON.stringify(expected),'Marquee speed/visible-only/invert changed expected layer membership');
      await page.locator('#invertBoxSelect').uncheck();
      await page.locator('#clearLayerSelection').click();
      h.check(await h.snapshot(page)===original,'Marquee changed saved shape transforms');
      checks.push(`marquee/${visible}/${speed}/${invert}`);
    }
    await page.locator('#boxVisibleOnly').check();
    await h.saveAs(page,'Handmade tool checkpoint');
    await page.evaluate(()=>flushPendingAutosave());
    await page.screenshot({path:path.join(output,'handmade-tools.png')});
    return {initial,checks,rows:trace.rows,exactArtwork:true,sampleOracle:'Existing independently unit-tested sampler; actual UI wiring and result checked here'};
  } finally {await trace.close();}
}
