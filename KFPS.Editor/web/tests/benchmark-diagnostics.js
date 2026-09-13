async page => {
  await page.evaluate(async () => {
    await loadPayload({shapes:[...Array.from({length:2999},(_,i)=>({type:editorCatalog.resourceToTypeCode('Primitives',1),data:[-720+(i%60)*24,-600+Math.floor(i/60)*24,.12,.12,0,0,0],color:[90,130,180,255]})),
      {type:editorCatalog.resourceToTypeCode('Primitives',27),data:[0,0,2,2,0,0,0],color:[215,90,120,255]}]});
    const image=document.createElement('canvas'); image.width=6000; image.height=4000;
    const ctx=image.getContext('2d'); ctx.fillStyle='#538ea1';ctx.fillRect(0,0,6000,4000);
    for(let i=0;i<90;i++){ctx.fillStyle=`hsl(${i*13%360} 45% 60%)`;ctx.fillRect(i*65,i*43,320,140);}
    await editorReference.loadOverlayImageFromUrl(image.toDataURL(),'synthetic-reference.png');image.width=image.height=1;
    setOverlayLayerMode('below');editorReference.image.set({opacity:.6,visible:true});
    window.diagnosticTarget=vinylObjects().at(-1);
    window.diagUntouched=JSON.stringify(snapshotShapes().slice(0,-1));
    window.diagMeasure=null;
    window.diagObserver=new PerformanceObserver(list=>{if(diagMeasure)diagMeasure.tasks.push(...list.getEntries().map(e=>e.duration));});
    diagObserver.observe({entryTypes:['longtask']});
    let previous=0;
    function frame(now){if(diagMeasure&&previous)diagMeasure.frames.push(now-previous);previous=now;window.diagTestFrame=requestAnimationFrame(frame);}
    requestAnimationFrame(frame);
    window.diagCacheCreates = 0;
    const createCache = fabric.Object.prototype._createCacheCanvas;
    fabric.Object.prototype._createCacheCanvas = function (...args) {
      if (this.kloudy) diagCacheCreates++;
      return createCache.apply(this, args);
    };
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
      await page.locator('[data-panel="propertiesPane"]').click();
      await page.waitForTimeout(350);
      await page.evaluate(()=>{diagMeasure={frames:[],tasks:[],cacheCreates:diagCacheCreates};});
      for(let repeat=0;repeat<12;repeat++) {
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
        const grab=await page.evaluate(()=>{
          const o=diagnosticTarget,m=o.calcTransformMatrix(),rect=canvas.upperCanvasEl.getBoundingClientRect();
          for(const [x,y] of [[0,0],[-.2,-.2],[.2,-.2],[-.2,.2],[.2,.2]]){
            const world=fabric.util.transformPoint(new fabric.Point(x*o.width,y*o.height),m);
            if(KfpsFabricAdapter.visiblePixelAt(canvas,o,world)){
              const p=fabric.util.transformPoint(world,canvas.viewportTransform);
              return {x:p.x+rect.left,y:p.y+rect.top,left:o.left,top:o.top};
            }
          }
          throw Error('No painted point found for real shape drag');
        });
        const direction=repeat%2?-1:1;
        await page.mouse.move(grab.x,grab.y);await page.mouse.down();
        await page.mouse.move(grab.x+direction*12,grab.y+direction*8,{steps:6});await page.mouse.up();
        if(!await page.evaluate(before=>Math.hypot(diagnosticTarget.left-before.left,diagnosticTarget.top-before.top)>5,grab))throw Error('Immediate post-rotation drag did not move the shape');
        await page.mouse.move(c.x,c.y);await page.mouse.down({button:'right'});
        await page.mouse.move(c.x+20,c.y+12,{steps:6});await page.mouse.up({button:'right'});
        for(const delta of [-160,160]){await page.mouse.wheel(0,delta);await page.waitForTimeout(100);}
      }
      await page.waitForTimeout(650);
      results.push(await page.evaluate(enabled=>{
        const measured=diagMeasure;diagMeasure=null;const frames=measured.frames.slice(1).sort((a,b)=>a-b);
        if(JSON.stringify(snapshotShapes().slice(0,-1))!==diagUntouched)throw Error('Benchmark changed unselected shapes');
        return {enabled,liveReadoutVisible:!document.getElementById('performancePane').hidden,frames:frames.length,frameP95:frames[Math.floor(frames.length*.95)],frameMax:Math.max(...frames),over100:frames.filter(v=>v>=100).length,longTasks:measured.tasks,
          layers:vinylObjects().length,selectedCorrect:canvas.getActiveObject()===diagnosticTarget,reference:[editorReference.image.width,editorReference.image.height],
          cacheCreates:diagCacheCreates-measured.cacheCreates};
      },enabled));
    }
    await page.evaluate(async()=>{KfpsEditorDiagnostics.setEnabled(true);await flushPendingAutosave();});
    await page.waitForTimeout(2200);
    return {fixture:'3000 layers; solid quarter circle; 24MP reference at 60%; rotation then immediate drag, pan and zoom',
      comparison:'ABBA reporting off/on; same properties pane, 650ms settled tail, 3000 layers and 24MP reference; no forced GC',results};
  } finally {await page.evaluate(()=>{KfpsEditorDiagnostics.setEnabled(true);diagObserver.disconnect();cancelAnimationFrame(diagTestFrame);});}
}
