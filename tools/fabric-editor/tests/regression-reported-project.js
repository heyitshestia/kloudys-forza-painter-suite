async page => {
  const fixture = process.env.KFPS_EDITOR_PROJECT_FIXTURE;
  if (!fixture) throw new Error("Set KFPS_EDITOR_PROJECT_FIXTURE to a private test project.");
  await page.setViewportSize({width:1600,height:1000});
  const content = fs.readFileSync(fixture,"utf8");
  await page.evaluate(async content => {
    await loadProjectFile(new File([content],"private-workflow.fabric-project.json",{type:"application/json"}));
    window.reportedOriginal = new Map(vinylObjects().map(o=>[o.kloudy.editor_id,JSON.stringify(objectToShape(o))]));
    window.reportedReference = sourceOverlayProjectState().data_url;
    overlayImage.set({opacity:.6});
  },content);
  const results=[];
  for(const slot of [27,36,39,2]) {
    const before=await page.evaluate(slot=>{
      const candidates=vinylObjects().filter(o=>o.kloudy.resource_family==="Primitives"&&o.kloudy.resource_index===slot);
      const o=candidates.sort((a,b)=>b.getScaledWidth()*b.getScaledHeight()-a.getScaledWidth()*a.getScaledHeight())[0];
      if(!o)throw new Error(`Fixture lacks slot ${slot}`);
      window.reportedTarget=o;
      const center=o.getCenterPoint(),zoom=Math.min(3,300/Math.max(o.getScaledWidth(),o.getScaledHeight()));
      canvas.setViewportTransform([zoom,0,0,zoom,canvas.width/2-center.x*zoom,canvas.height/2-center.y*zoom]);
      selectObjects([o],"private workflow"); o.setCoords(); canvas.renderAll();
      const rect=canvas.upperCanvasEl.getBoundingClientRect(),p=o.oCoords.mtr;
      const c=fabric.util.transformPoint(center,canvas.viewportTransform);
      return {id:o.kloudy.editor_id,angle:o.angle,rotate:{x:p.x+rect.left,y:p.y+rect.top},center:{x:c.x+rect.left,y:c.y+rect.top}};
    },slot);
    const r=before.rotate,c=before.center,dx=r.x-c.x,dy=r.y-c.y;
    await page.mouse.move(r.x,r.y);await page.mouse.down();
    await page.mouse.move(c.x+dx*Math.cos(.25)-dy*Math.sin(.25),c.y+dx*Math.sin(.25)+dy*Math.cos(.25),{steps:12});
    await page.mouse.up();
    const pick=await page.evaluate(()=>{
      const o=reportedTarget,surface=document.createElement("canvas");surface.width=canvas.width;surface.height=canvas.height;
      const ctx=surface.getContext("2d",{willReadFrequently:true}),cached=o.objectCaching;
      ctx.setTransform(...canvas.viewportTransform);
      try{o.objectCaching=false;o.render(ctx);}finally{o.objectCaching=cached;}
      const data=ctx.getImageData(0,0,surface.width,surface.height).data;
      const center=fabric.util.transformPoint(o.getCenterPoint(),canvas.viewportTransform);
      let point=null,distance=Infinity;
      for(let y=10;y<surface.height-10;y+=2)for(let x=10;x<surface.width-10;x+=2){
        if(data[(y*surface.width+x)*4+3]<120)continue;
        const d=(x-center.x)**2+(y-center.y)**2;
        if(d<distance){distance=d;point={x,y};}
      }
      surface.width=surface.height=1;
      if(!point)throw new Error("Could not find a filled point in the target shape");
      const rect=canvas.upperCanvasEl.getBoundingClientRect();
      return {x:point.x+rect.left,y:point.y+rect.top,left:o.left,top:o.top,angle:o.angle};
    });
    await page.mouse.move(pick.x,pick.y);await page.mouse.down();
    await page.mouse.move(pick.x+15,pick.y+9,{steps:12});await page.mouse.up();
    const resize=await page.evaluate(()=>{
      const o=reportedTarget;o.setCoords();const p=o.oCoords.br,rect=canvas.upperCanvasEl.getBoundingClientRect();
      return {left:o.left,top:o.top,scaleX:o.scaleX,scaleY:o.scaleY,x:p.x+rect.left,y:p.y+rect.top};
    });
    if(Math.hypot(resize.left-pick.left,resize.top-pick.top)<.01)throw new Error(`Slot ${slot}: move after rotation did not move the selected shape`);
    await page.mouse.move(resize.x,resize.y);await page.mouse.down();
    await page.mouse.move(resize.x+12,resize.y+12,{steps:12});await page.mouse.up();
    const after=await page.evaluate(()=>({angle:reportedTarget.angle,scaleX:reportedTarget.scaleX,scaleY:reportedTarget.scaleY,finite:reportedTarget.calcOwnMatrix().every(Number.isFinite)}));
    if(!after.finite||Math.abs(after.scaleX-resize.scaleX)+Math.abs(after.scaleY-resize.scaleY)<.00001)throw new Error(`Slot ${slot}: resize failed`);
    if(Math.abs(pick.angle-before.angle)<1)throw new Error(`Slot ${slot}: rotation failed`);
    results.push({slot,id:before.id,rotated:true,moved:true,resized:true});
  }
  const persistence=await page.evaluate(async ids=>{
    for(const o of vinylObjects())if(!ids.includes(o.kloudy.editor_id)&&reportedOriginal.get(o.kloudy.editor_id)!==JSON.stringify(objectToShape(o)))throw new Error("Gestures changed an unrelated layer");
    if(sourceOverlayProjectState().data_url!==reportedReference)throw new Error("Reference bytes changed");
    await flushPendingAutosave();
    if(!autosaveStatus.serverOk||!autosaveStatus.browserOk)throw new Error("Recovery not acknowledged");
    return {layers:vinylObjects().length,referencePreserved:true,recovery:autosaveStatus};
  },results.map(r=>r.id));
  return {results,persistence};
}
