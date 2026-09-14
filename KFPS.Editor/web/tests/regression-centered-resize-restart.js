async (page, options = {}) => {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const check=(value,message)=>{if(!value)throw Error(message);};
  await page.waitForFunction(()=>vinylObjects().length===3000&&!recoveryRestoreDepth&&!!editorReference.image);
  const state=await page.evaluate(()=>({centered:canvas.centeredScaling,stored:editorSettings.getItem('kloudyFabricCenteredResize'),
    checked:document.getElementById('resizeFromCenter').checked,name:currentProjectName}));
  check(state.centered&&state.checked&&state.stored==='1','Preference did not survive native restart');
  check(state.name==='Centered resize qualification','Recovery lost project association');
  const expected=await h.snapshot(page);
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({hasText:'Centered resize qualification'}).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(()=>!recoveryRestoreDepth&&!document.getElementById('projectBrowserDialog').open);
  check(await h.snapshot(page)===expected,'Saved project differs from recovered artwork');
  await page.evaluate(()=>{selectObjects([vinylObjects().at(-1)]);canvas.setViewportTransform([1.5,0,0,1.5,canvas.width/2,canvas.height/2]);canvas.renderAll();});
  await page.locator('[data-tool-mode="select"]').click();
  const generation=await page.evaluate(()=>documentGeneration);
  await page.locator('#resizeFromCenter').uncheck();await page.locator('#resizeFromCenter').check();
  check(await page.evaluate(()=>documentGeneration)===generation,'Preference changed document history');
  check(await h.snapshot(page)===expected,'Preference changed artwork');
  const rows=[];
  for(const handle of ['tl','tr','bl','br','ml','mr','mt','mb']) {
    const p=await page.evaluate(handle=>{
      const o=vinylObjects().at(-1);selectObjects([o]);o.setCoords();canvas.renderAll();
      const p=o.oCoords[handle],r=canvas.upperCanvasEl.getBoundingClientRect();
      return {x:p.x+r.left,y:p.y+r.top};
    },handle);
    await page.evaluate(()=>{
      guideState.guides=[];guideState.gridEnabled=true;guideState.snapGrid=true;guideState.gridSize=10;
      guideState.snapGuides=false;guideState.snapCtrlOnly=true;renderGuideObjects();
      window.edgeCenter=canvas.getActiveObject().getCenterPoint();window.edgeBefore=JSON.stringify(snapshotShapes());
    });
    await h.drag(page,p,{x:p.x+19,y:p.y+13},['Control']);
    const result=await page.evaluate(handle=>{
      const o=canvas.getActiveObject(),c=o.getCenterPoint(),kind=({ml:'left',mr:'right',mt:'top',mb:'bottom'})[handle]||handle;
      const p=objectCornerCoords(o)[kind];
      return {handle,drift:Math.hypot(c.x-edgeCenter.x,c.y-edgeCenter.y),gridDistance:Math.min(Math.abs(p.x/10-Math.round(p.x/10))*10,Math.abs(p.y/10-Math.round(p.y/10))*10)};
    },handle);
    check(result.drift<1e-5&&result.gridDistance<1e-5,'Grid snap failed '+JSON.stringify(result));rows.push(result);
    await page.locator('#undoBtn').click();await page.waitForFunction(()=>JSON.stringify(snapshotShapes())===edgeBefore);
  }
  await page.evaluate(()=>{guideState.gridEnabled=false;guideState.snapGuides=false;renderGuideObjects();});
  const skewResults=[];
  for(const on of [false,true])for(const handle of ['tl','tr','bl','br']) {
    await page.locator('#resizeFromCenter').setChecked(on);
    const p=await page.evaluate(handle=>{
      const o=vinylObjects().at(-1);selectObjects([o]);o.setCoords();canvas.renderAll();
      const p=o.oCoords[handle],r=canvas.upperCanvasEl.getBoundingClientRect();window.edgeBefore=JSON.stringify(snapshotShapes());
      return {x:p.x+r.left,y:p.y+r.top,skew:o.skewX};
    },handle);
    await h.drag(page,p,{x:p.x+28,y:p.y+9},['Shift']);
    const after=await page.evaluate(()=>({skew:canvas.getActiveObject().skewX,shape:objectToShape(canvas.getActiveObject())}));
    check(Math.abs(after.skew-p.skew)>.01,'Shift did not skew');skewResults.push({on,handle,...after});
    await page.locator('#undoBtn').click();await page.waitForFunction(()=>JSON.stringify(snapshotShapes())===edgeBefore);
  }
  for(let i=0;i<4;i++)check(JSON.stringify(skewResults[i].shape)===JSON.stringify(skewResults[i+4].shape),'Resize preference changed Shift skew');
  await page.locator('#resizeFromCenter').check();
  for(const handle of ['tl','tr','bl','br','ml','mr','mt','mb']) {
    const p=await page.evaluate(handle=>{
      selectObjects([vinylObjects().at(-1)]);const o=canvas.getActiveObject();o.set({lockScalingX:true,lockScalingY:true});o.setCoords();canvas.renderAll();
      const p=o.oCoords[handle],r=canvas.upperCanvasEl.getBoundingClientRect();window.edgeBefore=JSON.stringify(snapshotShapes());
      return {x:p.x+r.left,y:p.y+r.top};
    },handle);
    await h.drag(page,p,{x:p.x+22,y:p.y+19},['Control']);
    check(await page.evaluate(()=>JSON.stringify(snapshotShapes())===edgeBefore),'Centered resize ignored a scaling lock');
    await page.evaluate(()=>canvas.getActiveObject().set({lockScalingX:false,lockScalingY:false}));
  }
  for(const handle of ['br','mr','mb']) {
    const p=await page.evaluate(handle=>{
      const o=vinylObjects().at(-1);selectObjects([o]);o.setCoords();canvas.renderAll();
      const p=o.oCoords[handle],r=canvas.upperCanvasEl.getBoundingClientRect();
      const v=fabric.util.transformPoint(new fabric.Point(handle==='mb'?0:o.width/2*(o.flipX?-1:1),
        handle==='mr'?0:o.height/2*(o.flipY?-1:1)),o.calcTransformMatrix(),true);
      window.edgeBefore=JSON.stringify(snapshotShapes());window.edgeCenter=o.getCenterPoint();
      return {x:p.x+r.left,y:p.y+r.top,dx:-1.5*v.x*canvas.getZoom(),dy:-1.5*v.y*canvas.getZoom(),flipX:o.flipX,flipY:o.flipY};
    },handle);
    await h.drag(page,p,{x:p.x+p.dx,y:p.y+p.dy});
    const after=await page.evaluate(()=>{const o=canvas.getActiveObject(),c=o.getCenterPoint();return {
      drift:Math.hypot(c.x-edgeCenter.x,c.y-edgeCenter.y),flipX:o.flipX,flipY:o.flipY,finite:o.calcTransformMatrix().every(Number.isFinite)};});
    check(after.drift<1e-5&&after.finite,'Cross-center drag lost center or produced invalid geometry');
    check(handle==='mb'||p.flipX!==after.flipX,'Cross-center resize did not flip horizontally');
    check(handle==='mr'||p.flipY!==after.flipY,'Cross-center resize did not flip vertically');
    await page.locator('#undoBtn').click();await page.waitForFunction(()=>JSON.stringify(snapshotShapes())===edgeBefore);
  }
  const numeric=[];
  for(const on of [false,true]) {
    await page.locator('#resizeFromCenter').setChecked(on);
    await page.evaluate(()=>{selectObjects([vinylObjects().at(-1)]);window.edgeBefore=JSON.stringify(snapshotShapes());});
    await page.locator('#sxInput').fill('1.67');await page.locator('#sxInput').press('Enter');
    await page.waitForFunction(()=>JSON.stringify(snapshotShapes())!==edgeBefore);
    numeric.push(await page.evaluate(()=>JSON.stringify(objectToShape(vinylObjects().at(-1)))));
    await page.locator('#undoBtn').click();await page.waitForFunction(()=>JSON.stringify(snapshotShapes())===edgeBefore);
  }
  check(numeric[0]===numeric[1],'Resize preference changed numeric size entry');
  await page.locator('#resizeFromCenter').uncheck();
  await page.locator('#editorLanguageSelect').selectOption('ko');
  await page.evaluate(async()=>{if(!await KfpsEditorPreferences.flush())throw Error('Settings write failed');});
  await page.reload();
  await page.waitForFunction(()=>window.KfpsDesktop?.ready&&typeof canvas!=='undefined'&&!!canvas);
  check(await page.locator('#resizeFromCenter').isChecked()===false,'Disabled preference lost on reload');
  check(await page.evaluate(()=>KfpsI18n.language)==='ko','Korean language missing');
  check((await page.locator('label').filter({has:page.locator('#resizeFromCenter')}).innerText()).includes('중심 기준 크기 조절'),'Korean label missing');
  await page.evaluate(()=>{selectObjects([vinylObjects().at(-1)]);canvas.renderAll();});
  await page.locator('#resizeFromCenter').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output,'centered-resize-ko.png')});
  await page.locator('#resizeFromCenter').check();
  await page.evaluate(async()=>{await KfpsEditorPreferences.flush();});
  return {fullProcessRestart:true,projectReopenExact:true,preferenceNotArtwork:true,grid:rows,shiftUnchanged:true,korean:true};
}
