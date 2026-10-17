async page => {
  const check=(ok,message)=>{if(!ok)throw Error(message);};
  await page.evaluate(async()=>{
    $('layerSearch').value = '';
    await loadPayload({shapes:Array.from({length:3000},(_,i)=>({type:1048677,color:[60,150,200,i%2?255:120],
      data:[(i%60)*25-750,Math.floor(i/60)*25-600,.2,.15,i%90,0,0],editor_id:`edge-${i}`,
      editor_hidden:i===4,editor_locked:i===5,
      ...(i<1000?{editor_group_id:'target',editor_group_name:'Target'}:{})}))});
    selectObjects(vinylObjects().slice(1000),'test');
    window.__edgeNative=JSON.stringify(vinylObjects().map(o=>objectToShape(o,{includeEditorMeta:false})));
    window.__edgeBefore=JSON.stringify(snapshotShapes());
  });
  const bulk=await page.evaluate(()=>{
    const start=performance.now();
    const added=editorLayerGroups.addToGroup(selectedVinylObjects(),'target');
    return {added,ms:performance.now()-start,groups:membersForGroupIds(['target']).length,
      nativeSame:__edgeNative===JSON.stringify(vinylObjects().map(o=>objectToShape(o,{includeEditorMeta:false})))};
  });
  check(bulk.added&&bulk.groups===3000&&bulk.nativeSame,'Bulk grouping changed artwork');
  await page.locator('#undoBtn').click();await page.waitForFunction(()=>!editorCommands.busy);
  check(await page.evaluate(()=>JSON.stringify(snapshotShapes())===__edgeBefore),'Bulk undo mismatch');
  await page.locator('#redoBtn').click();await page.waitForFunction(()=>!editorCommands.busy);
  check(await page.evaluate(()=>membersForGroupIds(['target']).length===3000),'Bulk redo mismatch');
  await page.evaluate(()=>{selectObjects([vinylObjects()[1000]],'test');lastLayerListKey=layerListObjectKey(vinylObjects()[1000]);copySelectedLayers();});
  const beforeFull=await page.evaluate(()=>JSON.stringify(snapshotShapes()));
  await page.locator('#pasteLayer').click();await page.waitForFunction(()=>!editorCommands.busy);
  check(await page.evaluate(()=>JSON.stringify(snapshotShapes()))===beforeFull,'Capacity failure modified document');
  await page.evaluate(async()=>{
    await loadPayload({shapes:[
      {type:1048677,color:[30,120,180,255],data:[0,0,1,1,0,0,0],editor_id:'one',editor_group_id:'single',editor_group_name:'Single'},
      {type:1048677,color:[230,120,180,255],data:[500,0,.3,.3,0,0,0],editor_id:'two'}]});
    refreshLayers();
  });
  await page.locator('[data-layer-list-key="group:single"] .layerGroupTitle').click();
  await page.locator('#copyLayer').click();await page.locator('#pasteLayer').click();await page.waitForFunction(()=>!editorCommands.busy);
  check(await page.evaluate(()=>!!selectedVinylObjects()[0].kloudy.group_id&&selectedVinylObjects()[0].kloudy.group_id!=='single'),'One-member group copy lost explicit group');
  await page.locator('#undoBtn').click();await page.waitForFunction(()=>!editorCommands.busy);
  await page.evaluate(()=>{const one=vinylObjects()[0];selectObjects([one],'test');lastLayerListKey=layerListObjectKey(one);});
  await page.locator('#copyLayer').click();await page.locator('#pasteLayer').click();await page.waitForFunction(()=>!editorCommands.busy);
  check(await page.evaluate(()=>!selectedVinylObjects()[0].kloudy.group_id),'Individual from one-member group retained grouping');
  await page.locator('#groupActions').click(); await page.locator('#addSelectedToGroup').click();
  const cancelled=await page.evaluate(()=>JSON.stringify(snapshotShapes()));
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>!$('addToGroupDialog').open&&!$('addToGroupDialog').__selection);
  check(await page.evaluate(()=>JSON.stringify(snapshotShapes()))===cancelled,'Cancel changed membership');
  await page.evaluate(()=>{
    const one=vinylObjects()[0];selectObjects([one],'test');toggleSelectionLock();
    $('layerSearch').value='no match';refreshLayers();canvas.setZoom(1);centerCanvasOnObject(one);
  });
  const box=await page.locator('.upper-canvas').boundingBox();
  await page.mouse.dblclick(box.x+box.width/2,box.y+box.height/2);
  check(await page.locator('#layerSearch').inputValue()==='no match','Navigation bypassed selection lock');
  await page.evaluate(()=>{releaseSelectionLock('');$('layerSearch').value='';refreshLayers();});
  const visuals=[];
  for(const theme of ['blackout','whiteout']) {
    await page.evaluate(theme=>editorTheme.applyEditorTheme(theme,{persist:false}),theme);
    await page.evaluate(()=>openColorDialog());
    check(await page.locator('#favoriteColorGrid button').count()===16,'Palette slot count changed');
    const layout=await page.locator('#favoriteColorGrid').evaluate(e=>({width:e.clientWidth,scroll:e.scrollWidth,
      labels:[...e.querySelectorAll('button')].every(b=>b.scrollWidth<=b.clientWidth+2)}));
    check(layout.width>=layout.scroll&&layout.labels,'Palette labels overflow');
    await page.screenshot({path:path.join(output,`palette-${theme}.png`)});
    await page.locator('#closeColorDialog').click();
    visuals.push({theme,...layout});
  }
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Workflow edge regression');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
  await page.evaluate(async()=>{await flushPendingAutosave();});
  return {bulk,capacityGuard:true,singleMemberCopyModes:true,cancel:true,selectionLock:true,visuals};
}
