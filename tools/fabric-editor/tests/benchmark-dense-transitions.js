// Real native UI gestures. Private mixed-artwork fixtures are written only to the test profile.
async page => {
  const sourcePath=process.env.KFPS_EDITOR_PROJECT_FIXTURE;
  if(!sourcePath)throw new Error('Set KFPS_EDITOR_PROJECT_FIXTURE to a private mixed-shape project');
  const source=JSON.parse(fs.readFileSync(sourcePath,'utf8'));
  const counts=JSON.parse(process.env.KFPS_DENSE_COUNTS||'[1000,2000,3000]');
  const repeats=Number(process.env.KFPS_DENSE_REPEATS||4);
  const duration=Number(process.env.KFPS_DENSE_MINUTES||0)*60000;
  const profileCpu=process.env.KFPS_DENSE_PROFILE!=='0';
  const results=[];
  const crypto=require('node:crypto');
  const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  page.setDefaultTimeout(30000);
  const cdp=await page.context().newCDPSession(page);
  await page.evaluate(()=>{
    window.denseMeasure=null;
    new PerformanceObserver(list=>{if(denseMeasure)denseMeasure.tasks.push(...list.getEntries().map(e=>e.duration));}).observe({entryTypes:['longtask']});
    let last=performance.now();
    const frame=now=>{if(denseMeasure&&denseMeasure.frames.length<15000)denseMeasure.frames.push(now-last);last=now;requestAnimationFrame(frame);};
    requestAnimationFrame(frame);
    window.denseInput=[];
    for(const name of ['pointerdown','pointerup','wheel'])canvas.upperCanvasEl.addEventListener(name,e=>{
      if(denseMeasure){denseInput.push({event:name,time:performance.now(),target:canvas._currentTransform?.target?.kloudy?.editor_id||null,corner:canvas._currentTransform?.corner||null});if(denseInput.length>400)denseInput.shift();}
    },{passive:true});
    window.denseGeometry=()=>{
      const o=canvas.getActiveObject();
      if(!o||o.kloudy?.editor_id!==window.denseTarget)throw new Error('Dense gesture selected the wrong shape');
      if(!document.hasFocus()||document.hidden)throw new Error('Native editor lost focus');
      const box=canvas.upperCanvasEl.getBoundingClientRect();
      const screen=p=>{const t=fabric.util.transformPoint(p,canvas.viewportTransform);return{x:box.left+t.x,y:box.top+t.y};};
      const matrix=o.calcTransformMatrix();
      let grab=null;
      for(const [x,y] of [[0,0],[-.2,-.2],[.2,.2],[-.2,.2],[.2,-.2],[-.32,-.32],[.32,.32]]){
        const p=fabric.util.transformPoint(new fabric.Point(o.width*x,o.height*y),matrix);
        if(KfpsFabricAdapter.visiblePixelAt(canvas,o,p)){grab=screen(p);break;}
      }
      if(!grab)throw new Error('No painted interior point found');
      const pt=p=>({x:box.left+p.x,y:box.top+p.y});
      return {id:o.kloudy.editor_id,center:screen(o.getCenterPoint()),grab,rotate:pt(o.oCoords.mtr),right:pt(o.oCoords.mr),
        left:o.left,top:o.top,angle:o.angle,scaleX:o.scaleX,scaleY:o.scaleY,zoom:canvas.getZoom(),view:canvas.viewportTransform.slice()};
    };
  });
  const geometry=()=>page.evaluate(()=>denseGeometry());
  const drag=async(a,b)=>{await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:6});await page.mouse.up();};
  const stopMeasure=()=>page.evaluate(()=>{
    const m=denseMeasure;denseMeasure=null;
    const frames=m.frames.slice(1).sort((a,b)=>a-b);
    return {frames:frames.length,p50:frames[Math.floor(frames.length*.5)]||0,p95:frames[Math.floor(frames.length*.95)]||0,
      p99:frames[Math.floor(frames.length*.99)]||0,max:Math.max(0,...frames),gaps100:frames.filter(x=>x>=100).length,gaps250:frames.filter(x=>x>=250).length,gaps500:frames.filter(x=>x>=500).length,
      tasks:m.tasks,input:denseInput.splice(0),diagnostics:KfpsEditorDiagnostics.snapshot()};
  });
  for(const count of counts){
    const shapeCount=count-3,tiles=Math.ceil(shapeCount/source.shapes.length),cols=Math.ceil(Math.sqrt(tiles)),rows=Math.ceil(tiles/cols);
    const shapes=Array.from({length:shapeCount},(_,i)=>{
      const tile=Math.floor(i/source.shapes.length),s=structuredClone(source.shapes[i%source.shapes.length]);
      s.data[0]=s.data[0]*.4+(tile%cols-(cols-1)/2)*620;
      s.data[1]=s.data[1]*.4+(Math.floor(tile/cols)-(rows-1)/2)*520;
      s.data[2]*=.4;s.data[3]*=.4;
      return {...s,editor_id:`dense-${i}`,shape_name:`${i<50?'Batch50':'Background'} ${i}`,editor_group_id:i<50?'dense-group':null,
        editor_group_name:i<50?'Batch50':null,editor_locked:false,editor_hidden:false};
    });
    for(const [slot,x,y] of [[30,0,0],[36,-500,0],[39,500,0]])shapes.push({type:1048576+100+slot,type_word:100+slot,resource_family:'Primitives',resource_index:slot,
      data:[x,y,2.4,2.4,0,0,0],color:[210,80+slot,130,255],editor_id:`target-${slot}`,shape_name:`Transition target ${slot}`});
    const project={...structuredClone(source),name:`Dense transitions ${count}`,layer_count:count,shapes,editor_guides:[],editor_collapsed_groups:[]};
    project.editor_source_overlay.transform.opacity=.65;
    project.editor_source_overlay.controls.opacity_percent=65;
    const folder=path.join(output,'profile','projects');fs.mkdirSync(folder,{recursive:true});
    const fixtureFile=path.join(folder,`${project.name}.fabric-project.json`);
    fs.writeFileSync(fixtureFile,JSON.stringify(project));
    if(await page.evaluate(()=>documentDirty)){
      await page.locator('#saveProject').click();await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
    }
    await page.locator('#loadProject').click();
    await page.locator('.projectBrowserEntry').filter({hasText:project.name}).click();
    await page.locator('#selectProjectEntry').click();
    await page.waitForFunction(n=>vinylObjects().length===n&&overlayImage&&!documentDirty,count);
    await page.locator('#fitView').click();
    const loaded=await page.evaluate(()=>({layers:vinylObjects().length,reference:[overlayImage.width,overlayImage.height],visible:vinylObjects().filter(o=>o.isOnScreen()).length}));
    if(loaded.visible<count*.9)throw new Error('Dense fixture hides too many shapes offscreen: '+JSON.stringify(loaded));
    await page.screenshot({path:path.join(output,`dense-${count}-loaded.png`)});
    const stageStart=Date.now();
    for(let round=0;round===0||Date.now()-stageStart<duration;round++){
    for(const mode of ['below','above'])for(const slot of [30,36,39]){
      await page.locator('[data-panel="overlayPane"]').click();
      await page.locator('#overlayLayerMode').selectOption(mode);
      await page.locator('#layerSearch').fill(`Transition target ${slot}`);
      await page.locator('.layerRow').filter({hasText:`Transition target ${slot}`}).click();
      await page.evaluate(slot=>{window.denseTarget=`target-${slot}`;},slot);
      await page.locator('[data-panel="performancePane"]').click();
      const untouched=digest(await page.evaluate(()=>vinylObjects().filter(o=>o.kloudy.editor_id!==denseTarget).map(o=>objectToShape(o))));
      if(profileCpu){await cdp.send('Profiler.enable');await cdp.send('Profiler.start');}
      await page.evaluate(()=>{denseInput=[];denseMeasure={frames:[],tasks:[]};});
      const transitions=[];
      for(let i=0;i<repeats;i++){
        const b=await geometry(),c=b.center,r=b.rotate,dx=r.x-c.x,dy=r.y-c.y,turn=.32*(i%2?-1:1);
        await page.mouse.move(r.x,r.y);await page.mouse.down();
        for(let step=1;step<=8;step++){const a=turn*step/8;await page.mouse.move(c.x+dx*Math.cos(a)-dy*Math.sin(a),c.y+dx*Math.sin(a)+dy*Math.cos(a));}
        await page.mouse.up();
        const rotated=await geometry();
        await drag(rotated.grab,{x:rotated.grab.x+(i%2?-8:8),y:rotated.grab.y+(i%2?-5:5)});
        const moved=await geometry();
        if(Math.abs(rotated.angle-b.angle)<5||Math.hypot(moved.left-rotated.left,moved.top-rotated.top)<2)throw new Error('Rotate-immediate-move did not transform target');
        await page.mouse.move(moved.grab.x,moved.grab.y);
        await page.mouse.wheel(0,-120);await page.mouse.wheel(0,120);await page.mouse.wheel(0,-120);await page.mouse.wheel(0,120);
        const zoomed=await geometry();
        await drag(zoomed.grab,{x:zoomed.grab.x+(i%2?8:-8),y:zoomed.grab.y+(i%2?5:-5)});
        const after=await geometry();
        if(Math.hypot(after.left-zoomed.left,after.top-zoomed.top)<2)throw new Error('Zoom-immediate-move did not move target');
        transitions.push({before:b,rotated,moved,zoomed,after});
      }
      const measured=await stopMeasure();
      const profile=profileCpu?(await cdp.send('Profiler.stop')).profile:{nodes:[],samples:[]};
      const functions=new Map(profile.nodes.map(n=>[n.id,n.callFrame]));const cpu=new Map();
      for(let i=0;i<(profile.samples||[]).length;i++){const f=functions.get(profile.samples[i]);const name=`${f.functionName||'anonymous'} ${f.url.split('/').pop()}:${f.lineNumber+1}`;cpu.set(name,(cpu.get(name)||0)+(profile.timeDeltas[i]||0)/1000);}
      if(untouched!==digest(await page.evaluate(()=>vinylObjects().filter(o=>o.kloudy.editor_id!==denseTarget).map(o=>objectToShape(o)))))throw new Error('Dense gesture changed unrelated layers');
      const row={count,round,elapsedMs:Date.now()-stageStart,mode,slot,loaded,transitions,measured,topCpu:[...cpu].sort((a,b)=>b[1]-a[1]).slice(0,20),heap:await cdp.send('Runtime.getHeapUsage'),dom:await cdp.send('Memory.getDOMCounters')};
      results.push(row);fs.writeFileSync(path.join(output,'dense-progress.json'),JSON.stringify(results,null,2));
      console.log(JSON.stringify({dense:count,round,elapsedMs:row.elapsedMs,mode,slot,cycles:repeats,p95:measured.p95,max:measured.max,gaps250:measured.gaps250,gaps500:measured.gaps500,heap:row.heap.usedSize,domNodes:row.dom.nodes}));
    }
    }
    await page.locator('#saveProject').click();await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
    await page.evaluate(()=>flushPendingAutosave());
    await page.screenshot({path:path.join(output,`dense-${count}-tested.png`)});
  }
  await cdp.detach();
  if(errors.length)throw new Error(errors.join('\n'));
  return {cases:results.length,counts,repeats,errors,sourceDigest:digest(source),resultsFile:'dense-progress.json'};
}
