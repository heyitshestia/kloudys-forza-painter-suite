async page => {
  await page.evaluate(async () => {
    await loadPayload({shapes:[...Array.from({length:499},(_,i)=>({type:resourceToTypeCode('Primitives',1),data:[-650+(i%25)*52,-500+Math.floor(i/25)*52,.25,.25,0,0,0],color:[90,130,180,255]})),
      {type:resourceToTypeCode('Primitives',27),data:[0,0,2,2,0,0,0],color:[215,90,120,255]}]});
    const image=document.createElement('canvas'); image.width=1000; image.height=1500;
    const ctx=image.getContext('2d'); ctx.fillStyle='#538ea1';ctx.fillRect(0,0,1000,1500);
    await loadOverlayImageFromUrl(image.toDataURL(),'synthetic-reference.png');image.width=image.height=1;
    overlayLayerMode='below';overlayImage.set({opacity:.6,visible:true});
    window.diagnosticTarget=vinylObjects().at(-1);
    window.diagMeasure=null;
    window.diagObserver=new PerformanceObserver(list=>{if(diagMeasure)diagMeasure.tasks.push(...list.getEntries().map(e=>e.duration));});
    diagObserver.observe({entryTypes:['longtask']});
    let previous=0;
    function frame(now){if(diagMeasure&&previous)diagMeasure.frames.push(now-previous);previous=now;window.diagTestFrame=requestAnimationFrame(frame);}
    requestAnimationFrame(frame);
  });
  const results=[];
  try {
    for(const enabled of [false,true,true,false]) {
      await page.evaluate(enabled=>{
        KfpsEditorDiagnostics.setEnabled(enabled);
        diagnosticTarget.set({left:0,top:0,angle:0});diagnosticTarget.setCoords();
        canvas.setViewportTransform([1,0,0,1,canvas.width/2,canvas.height/2]);
        selectObjects([diagnosticTarget],'benchmark');canvas.renderAll();
      },enabled);
      await page.locator(`[data-panel="${enabled ? 'performancePane' : 'propertiesPane'}"]`).click();
      await page.waitForTimeout(350);
      await page.evaluate(()=>{diagMeasure={frames:[],tasks:[]};});
      for(let repeat=0;repeat<4;repeat++) {
        const geometry=await page.evaluate(()=>{
          diagnosticTarget.setCoords();const rect=canvas.upperCanvasEl.getBoundingClientRect();
          const p=point=>({x:rect.left+point.x,y:rect.top+point.y});
          return {center:p(fabric.util.transformPoint(diagnosticTarget.getCenterPoint(),canvas.viewportTransform)),handle:p(diagnosticTarget.oCoords.mtr),angle:diagnosticTarget.angle};
        });
        const {center:c,handle:r}=geometry,dx=r.x-c.x,dy=r.y-c.y;
        await page.mouse.move(r.x,r.y);await page.mouse.down();
        for(let step=1;step<=12;step++) {const a=step*.025*(repeat%2?-1:1);await page.mouse.move(c.x+dx*Math.cos(a)-dy*Math.sin(a),c.y+dx*Math.sin(a)+dy*Math.cos(a));}
        await page.mouse.up();
        const valid=await page.evaluate(before=>canvas.getActiveObject()===diagnosticTarget&&Math.abs(diagnosticTarget.angle-before)>5,geometry.angle);
        if(!valid)throw new Error('Wrong object selected or rotation did not occur');
        await page.mouse.move(c.x,c.y);await page.mouse.down({button:'right'});
        await page.mouse.move(c.x+20,c.y+12,{steps:6});await page.mouse.up({button:'right'});
        for(const delta of [-160,160]){await page.mouse.wheel(0,delta);await page.waitForTimeout(100);}
      }
      await page.waitForTimeout(200);
      results.push(await page.evaluate(enabled=>{
        const measured=diagMeasure;diagMeasure=null;const frames=measured.frames.slice(1).sort((a,b)=>a-b);
        return {enabled,liveReadoutVisible:!document.getElementById('performancePane').hidden,frameP95:frames[Math.floor(frames.length*.95)],frameMax:Math.max(...frames),longTasks:measured.tasks,
          layers:vinylObjects().length,selectedCorrect:canvas.getActiveObject()===diagnosticTarget,reference:[overlayImage.width,overlayImage.height]};
      },enabled));
    }
    await page.evaluate(async()=>{KfpsEditorDiagnostics.setEnabled(true);await flushPendingAutosave();});
    await page.waitForTimeout(2200);
    return {fixture:'500 layers; solid quarter circle; 1.5MP reference at 60%; same pointer gestures',results};
  } finally {await page.evaluate(()=>{KfpsEditorDiagnostics.setEnabled(true);diagObserver.disconnect();cancelAnimationFrame(diagTestFrame);});}
}
