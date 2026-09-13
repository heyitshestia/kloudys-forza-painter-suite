async (page, options = {}) => {
  const h=require(path.join(__dirname,'handmade-project-fixture.cjs'));
  const initial=await h.setup(page,output,options), rows=[];
  const id=await page.evaluate(()=>vinylObjects().filter(o=>o.kloudy.resource_family==='Primitives'&&o.kloudy.resource_index===36)
    .sort((a,b)=>b.getScaledWidth()*b.getScaledHeight()-a.getScaledWidth()*a.getScaledHeight())[0].kloudy.editor_id);
  const sample=()=>page.evaluate(()=>{
    const o=canvas.getActiveObject(), matrix=o.calcTransformMatrix(), rect=canvas.upperCanvasEl.getBoundingClientRect(), points=[];
    for(const x of [0,-.15,.15,-.3,.3,-.42,.42])for(const y of [0,-.15,.15,-.3,.3,-.42,.42]) {
      const p=fabric.util.transformPoint(new fabric.Point(o.width*x,o.height*y),matrix);
      const q=fabric.util.transformPoint(p,canvas.viewportTransform);
      points.push({local:[x,y],scene:[p.x,p.y],screen:{x:q.x+rect.left,y:q.y+rect.top},
        helper:KfpsFabricAdapter.visiblePixelAt(canvas,o,p),normal:!canvas.isTargetTransparent(o,q.x,q.y)});
    }
    return {data:objectToShape(o).data,points,helperHits:points.filter(p=>p.helper).length,normalHits:points.filter(p=>p.normal).length,
      bounds:KfpsFabricAdapter.sceneBounds(o),width:o.width,height:o.height,zoom:canvas.getZoom(),preview:editorRenderer.active};
  });
  for(const speed of options.speeds || Object.keys(h.speeds)) {
    await h.selectId(page,id);const before=await h.snapshot(page);
    await page.locator('#bringFront').click();await h.frameSelection(page);
    const g=await h.geometry(page), r=g.handles.mtr,c=g.center,dx=r.x-c.x,dy=r.y-c.y,turn=.23;
    await h.motion(page,r,{x:c.x+dx*Math.cos(turn)-dy*Math.sin(turn),y:c.y+dx*Math.sin(turn)+dy*Math.cos(turn)},speed);
    const after=await sample();
    const hit=after.points.find(p=>p.normal);
    h.check(hit,'Actual native picking has no painted sample');
    await h.motion(page,hit.screen,{x:hit.screen.x+16,y:hit.screen.y+11},speed);
    const moved=await page.evaluate(()=>objectToShape(canvas.getActiveObject()).data);
    h.check(Math.hypot(moved[0]-after.data[0],moved[1]-after.data[1])>.01,'Actual painted point did not drag');
    rows.push({speed,after,moved,actualDrag:true});
    fs.writeFileSync(path.join(output,'picking-comparison.json'),JSON.stringify(rows,null,2));
    for(let i=0;i<4&&await h.snapshot(page)!==before;i++){
      await page.locator('#undoBtn').click();await page.waitForFunction(()=>!editorCommands.busy);
    }
    h.check(await h.snapshot(page)===before,'Picking characterization failed exact undo');
  }
  await h.saveAs(page,'Handmade picking characterization');
  return {initial,rows,diagnosticOnly:true,notTimingQualification:true};
}
