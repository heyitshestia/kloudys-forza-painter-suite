async page => {
  await page.evaluate(async()=>{
    await loadPayload({shapes:[{type:resourceToTypeCode('Primitives',2),data:[0,0,1,1,0,0,0],color:[120,190,220,255]}]});
    window.controlTarget=vinylObjects()[0];
  });
  const matrix=await page.evaluate(()=>{
    let cases=0;
    for(const zoom of [.35,1,2.5]) for(const [width,height] of [[3,40],[40,3],[3,3],[18,175],[175,18],[175,175]]) for(const angle of [0,37,90,153]){
      controlTarget.set({left:0,top:0,scaleX:width/controlTarget.width,scaleY:height/controlTarget.height,angle});
      canvas.setViewportTransform([zoom,0,0,zoom,canvas.width/2,canvas.height/2]);
      selectObjects([controlTarget],'control picking fixture');styleObjectTransformControls(controlTarget);controlTarget.setCoords();
      for(const [name,point] of Object.entries(controlTarget.oCoords)) for(const touch of [false,true]){
        const found=controlTarget._findTargetCorner(point,touch);
        if(found!==name)throw new Error(JSON.stringify({zoom,width,height,angle,name,touch,found}));
        cases++;
      }
    }
    controlTarget.setControlVisible('mb',false);
    const point=controlTarget.oCoords.mb;
    if(controlTarget._findTargetCorner(point,false)==='mb')throw new Error('Hidden control remained pickable');
    controlTarget.setControlVisible('mb',true);
    if(controlTarget._findTargetCorner({x:-1000,y:-1000},false))throw new Error('Outside point picked a control');
    canvas.discardActiveObject();
    if(controlTarget._findTargetCorner(point,false))throw new Error('Inactive object control remained pickable');
    return cases;
  });
  const drags=[];
  for(const [zoom,delay] of [[.8420537569564324,0],[.8420537569564324,100],[.35,0],[2.5,0]]){
    await page.evaluate(zoom=>{
      controlTarget.set({left:0,top:0,angle:0,scaleX:175/controlTarget.width,scaleY:175/controlTarget.height});
      canvas.setViewportTransform([zoom,0,0,zoom,canvas.width/2,canvas.height/2]);selectObjects([controlTarget],'small resize');controlTarget.setCoords();canvas.requestRenderAll();
    },zoom);
    await page.waitForTimeout(60);
    for(const [handle,dimension,wanted] of [['mr','width',21],['mb','height',25]]){
      const start=await page.evaluate(({handle,dimension})=>{
        const r=canvas.upperCanvasEl.getBoundingClientRect(),o=controlTarget;
        return {x:r.left+o.oCoords[handle].x,y:r.top+o.oCoords[handle].y,size:o[dimension]*o[dimension==='width'?'scaleX':'scaleY'],width:o.width*o.scaleX,height:o.height*o.scaleY};
      },{handle,dimension});
      await page.mouse.move(start.x,start.y);await page.mouse.down();
      if(await page.evaluate(()=>canvas._currentTransform?.corner)!==handle)throw new Error('Real pointer chose a neighboring handle');
      const delta=(wanted-start.size)*zoom;
      await page.mouse.move(start.x+(handle==='mr'?delta:0),start.y+(handle==='mb'?delta:0),{steps:17});await page.mouse.up();
      if(delay)await page.waitForTimeout(delay);
      const after=await page.evaluate(()=>({width:controlTarget.width*controlTarget.scaleX,height:controlTarget.height*controlTarget.scaleY}));
      const other=dimension==='width'?'height':'width';
      if(Math.abs(after[other]-start[other])>1e-6||Math.abs(after[dimension]-wanted)>2/zoom)throw new Error('Side resize changed wrong dimension: '+JSON.stringify({zoom,handle,start,after}));
      drags.push({zoom,delay,handle,after});
    }
  }
  await page.evaluate(()=>flushPendingAutosave());
  return {matrixCases:matrix,hiddenAndInactive:true,realPointerDrags:drags};
}
