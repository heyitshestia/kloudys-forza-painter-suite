async (page, options = {}) => {
  page.setDefaultTimeout(20000);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const idle = () => page.waitForFunction(() => !editorCommands.busy && !projectSaveInProgress);
  const blur = () => page.evaluate(() => document.activeElement?.blur());
  const row = async id => {
    const key = await page.evaluate(id => {
      const key = id.startsWith('group:') ? id : layerListObjectKey(vinylObjects().find(o=>o.kloudy.editor_id===id));
      const entry = layerListRows.get(key);
      if (!entry) throw Error('Missing row '+id);
      layerScrollPane().scrollTop = entry.virtualTop;
      renderVirtualLayerWindow(true);
      return key;
    }, id);
    return page.locator(`[data-layer-list-key="${key}"]`);
  };
  const select = async id => (await row(id)).locator(id.startsWith('group:') ? '.layerGroupTitle' : '.layerMain b').click();
  const shapes = () => page.evaluate(() => JSON.stringify(snapshotShapes()));
  const undoExact = async before => {
    await page.locator('#undoBtn').click(); await idle();
    check(await shapes() === before, 'Undo did not restore exact shape state');
    await page.locator('#redoBtn').click(); await idle();
  };
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({length:8}, (_,i)=>({type:1048677,
      data:[-500+i*140,0,.4,.4,0,0,0],color:[80,120,170,255],editor_id:`w${i}`,
      editor_group_id:i<2?'inner':i===2?'outer':null, editor_group_name:i<2?'Inner':i===2?'Outer':null,
      ...(i<2?{editor_group_path:[{id:'outer',name:'Outer'},{id:'inner',name:'Inner'}]}:{}) })) });
    favoriteColors = Array.from({length:16},(_,i)=>[20+i*10,80+i*4,200-i*6,255]);
    saveFavoriteColors(); renderFavoriteColors(); refreshLayers();
  });
  await select('w7'); await blur();
  for(let i=0;i<16;i++) {
    await page.keyboard.press(`${i>=8?'Control+':''}${i%8+1}`);
    check(await page.evaluate(i => JSON.stringify(objectToShape(selectedVinylObjects()[0]).color)===JSON.stringify(favoriteColors[i]),i), `Colour slot ${i+1} failed`);
  }
  await page.evaluate(()=>{favoriteColors[15]=null;saveFavoriteColors();});
  const emptyBefore=await shapes();
  await page.keyboard.press('Control+8'); check(await shapes()===emptyBefore,'Empty swatch changed artwork');
  await page.evaluate(()=>setObjectLocked(selectedVinylObjects()[0],true));
  const lockedBefore=await shapes();
  await page.keyboard.press('1'); check(await shapes()===lockedBefore,'Colour bypassed layer lock');
  await page.evaluate(()=>setObjectLocked(selectedVinylObjects()[0],false));
  await page.locator('#layerSearch').fill(''); await page.locator('#layerSearch').press('2');
  check((await page.locator('#layerSearch').inputValue())==='2','Typing was intercepted');
  await page.locator('#layerSearch').fill('');
  await page.evaluate(()=>{const e=document.createElement('div');e.id='ime-test';e.contentEditable='true';document.body.appendChild(e);e.focus();});
  const typingBefore=await shapes(); await page.keyboard.press('3');
  check(await shapes()===typingBefore,'Contenteditable recoloured shapes');
  await page.evaluate(()=>document.getElementById('ime-test').remove());
  await page.evaluate(()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'4',isComposing:true,bubbles:true})));
  check(await shapes()===typingBefore,'IME recoloured shapes');
  if (await page.locator('#workspaceHelpMenu').count()) await page.locator('#workspaceHelpMenu').click();
  await page.locator('#shortcutsBtn').click();
  await page.locator('[data-shortcut-action="colorSlot1"]').click();
  await page.keyboard.press('Control+Alt+9');
  check(await page.evaluate(()=>shortcutFor('colorSlot1')==='Ctrl+Alt+9'),'Shortcut UI did not rebind');
  await page.evaluate(()=>document.getElementById('shortcutsDialog').close());
  await blur(); await page.keyboard.press('Control+Alt+9');
  check(await page.evaluate(()=>JSON.stringify(objectToShape(selectedVinylObjects()[0]).color)===JSON.stringify(favoriteColors[0])),'Rebound shortcut failed');
  await page.evaluate(()=>{
    const saved=editorSettings.getItem(SHORTCUTS_KEY);
    editorSettings.setItem(SHORTCUTS_KEY,JSON.stringify({duplicate:'1'}));
    const loaded=loadShortcuts(); if(loaded.duplicate!=='1'||loaded.colorSlot1!=='')throw Error('Legacy custom binding overwritten');
    editorSettings.setItem(SHORTCUTS_KEY,saved);
  });
  // A real image upload exercises reference controls and the renderer, not a stub.
  await page.evaluate(()=>activateDockPanel('overlayPane'));
  const png=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=512;c.height=256;
    const x=c.getContext('2d');x.fillStyle='#219b8b';x.fillRect(0,0,512,256);return c.toDataURL().split(',')[1];});
  await page.locator('#overlayInput').setInputFiles({name:'workflow-reference.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
  await page.waitForFunction(()=>!!editorReference.image);
  await page.locator('#overlaySizeLock').click();
  const refBefore=await page.evaluate(()=>editorReference.sourceOverlayProjectState());
  await blur(); await page.keyboard.press('Space');
  check(await page.evaluate(()=>editorReference.image.visible===false),'Space did not hide reference');
  await page.keyboard.down('Space'); await page.keyboard.down('Space'); await page.keyboard.up('Space');
  check(await page.evaluate(()=>editorReference.image.visible===true),'Key repeat toggled reference twice');
  const refAfter=await page.evaluate(()=>editorReference.sourceOverlayProjectState());
  check(JSON.stringify(refBefore)===JSON.stringify(refAfter),'Reference toggle changed placement, opacity, source or lock');
  await page.locator('#overlaySizeLock').focus(); await page.keyboard.press('Space');
  check(await page.evaluate(()=>!editorReference.sizeLocked && editorReference.image.visible),'Space stole focused button activation');
  await page.evaluate(()=>{setToolRailMode('guides');guidePointer={clientX:300,clientY:300};});
  await blur(); await page.keyboard.down('Space');
  check(await page.evaluate(()=>guideSpacePan&&editorReference.image.visible),'Guide panning lost priority');
  await page.keyboard.up('Space'); await page.evaluate(()=>setToolRailMode('select'));
  // Copying an individual extracts only that shape. Complete subgroups stay intact.
  await select('w0'); await blur(); const copyBefore=await shapes();
  await page.keyboard.press('Control+c'); await page.keyboard.press('Control+v'); await idle();
  check(await page.evaluate(()=>selectedVinylObjects().length===1&&!selectedVinylObjects()[0].kloudy.group_id),'Single pasted shape retained a group');
  await undoExact(copyBefore); await page.locator('#undoBtn').click(); await idle();
  await select('group:inner'); await blur();
  await page.keyboard.press('Control+c'); await page.keyboard.press('Control+v'); await idle();
  check(await page.evaluate(()=>{const p=selectedVinylObjects().map(o=>KfpsEditorLayerGroups.objectPath(o));
    return p.length===2&&p.every(x=>x.length===1&&x[0].id!=='inner')&&p[0][0].id===p[1][0].id;}),'Complete child copy kept partial parent or lost group');
  await page.locator('#undoBtn').click(); await idle();
  // Group plus loose shape should extend, not create an accidental wrapper.
  await select('group:outer');
  await (await row('w3')).locator('.layerMain b').click({modifiers:['Control']});
  const extendBefore=await shapes(); await page.locator('#groupSelected').click();
  check(await page.evaluate(()=>vinylObjects().find(o=>o.kloudy.editor_id==='w3').kloudy.group_id==='outer'),'Group did not extend existing group');
  await undoExact(extendBefore);
  await select('w4'); await page.locator('#groupActions').click(); await page.locator('#addSelectedToGroup').click();
  await page.locator('#addToGroupTarget').selectOption('inner');
  await page.locator('#addToGroupDialog button[value=add]').click();
  check(await page.evaluate(()=>vinylObjects().find(o=>o.kloudy.editor_id==='w4').kloudy.group_id==='inner'),'Add to Group dialog failed');
  // Pointer drag to a collapsed group's centre adds membership without changing depth/geometry.
  await page.evaluate(()=>setCollapsedGroup('outer',true));
  await select('w5');
  const dragBefore=await shapes();
  const nativeBefore=await page.evaluate(()=>JSON.stringify(vinylObjects().map(o=>objectToShape(o,{includeEditorMeta:false}))));
  const source=await (await row('w5')).locator('.layerMain b').boundingBox();
  await page.mouse.move(source.x+source.width/2,source.y+source.height/2); await page.mouse.down();
  await page.mouse.move(source.x+source.width/2+8,source.y+source.height/2);
  const target=await (await row('group:outer')).boundingBox();
  await page.mouse.move(target.x+target.width/2,target.y+target.height/2,{steps:12});
  // Auto-scroll moves rows during the approach. Aim at the current header,
  // rather than asserting a centre-drop using its old viewport coordinates.
  const currentTarget=await page.locator('[data-layer-list-key="group:outer"]').boundingBox();
  await page.mouse.move(currentTarget.x+currentTarget.width/2,currentTarget.y+currentTarget.height/2);
  fs.writeFileSync(path.join(output,'drag-evidence.json'),JSON.stringify(await page.evaluate(({source,target})=>({source,target,
    drop:layerDragState?.dropSlot,entry:layerDragState?.key,scroll:layerScrollPane().scrollTop,
    hit:document.elementFromPoint(target.x+target.width/2,target.y+target.height/2)?.outerHTML}),{source,target}),null,2));
  check(await page.locator('[data-layer-list-key="group:outer"]').evaluate(e=>e.classList.contains('layerDropTarget')),'Missing drop-into feedback');
  await page.mouse.up();
  check(await page.evaluate(()=>vinylObjects().find(o=>o.kloudy.editor_id==='w5').kloudy.group_id==='outer'),'Pointer drop failed');
  check(await page.evaluate(()=>JSON.stringify(vinylObjects().map(o=>objectToShape(o,{includeEditorMeta:false}))))===nativeBefore,'Grouping changed native artwork');
  await undoExact(dragBefore);
  await select('group:outer'); await (await row('w6')).locator('.layerMain b').click({modifiers:['Control']});
  await page.locator('#groupActions').click(); await page.locator('#newSelectedGroup').click();
  check(await page.evaluate(()=>KfpsEditorLayerGroups.objectPath(vinylObjects().find(o=>o.kloudy.editor_id==='w0')).length===3),'Explicit parent group missing');
  const cycleBefore=await shapes();
  check(!await page.evaluate(()=>editorLayerGroups.addToGroup(selectedVinylObjects(),'inner')),'Cycle accepted');
  check(await shapes()===cycleBefore,'Rejected cycle changed artwork');
  // Save and reopen through the real project picker.
  if (await page.locator('#workspaceFileMenu').count()) await page.locator('#workspaceFileMenu').click();
  await page.locator('#saveProjectAs').click(); await page.locator('#textPromptInput').fill('Workflow regression');
  await page.locator('#textPromptInput').press('Enter'); await idle();
  await page.waitForFunction(()=>!documentDirty);
  const saved=await shapes();
  await page.reload(); await page.waitForFunction(()=>window.KfpsDesktop?.ready);
  await page.evaluate(()=>document.querySelectorAll('dialog[open]').forEach(d=>d.close()));
  await page.evaluate(()=>openProjectBrowser());
  await page.waitForFunction(()=>document.querySelectorAll('#projectBrowserEntries button').length>0);
  await page.locator('#projectBrowserEntries button').filter({hasText:'Workflow regression'}).dblclick();
  await idle(); await page.waitForFunction(()=>vinylObjects().length===8);
  check(await shapes()===saved,'Saved group metadata or shapes did not reopen exactly');
  check(await page.evaluate(()=>shortcutFor('colorSlot1')==='Ctrl+Alt+9'),'Shortcut did not persist');
  await page.screenshot({path:path.join(output,'workflow-groups.png')});
  // Large virtual list: locate a shape behind a collapsed group and a mismatched search.
  await page.evaluate(async()=>{
    await loadPayload({shapes:Array.from({length:3000},(_,i)=>({type:1048677,color:[50,150,210,255],
      data:[(i%60)*30-850,Math.floor(i/60)*25-600,.2,.15,0,0,0],editor_id:`dense-${i}`,
      ...(i<3?{editor_group_id:'dense-group',editor_group_name:'Dense group'}:{})}))});
    setToolRailMode('select'); canvas.discardActiveObject();
    setCollapsedGroup('dense-group',true); $('layerSearch').value='NOT FOUND';refreshLayers();
    const target=vinylObjects()[1]; canvas.setZoom(2);centerCanvasOnObject(target);
    window.__denseBefore=JSON.stringify(snapshotShapes());window.__denseHistory=editorHistory.index;
    window.__denseViewport=JSON.stringify(canvas.viewportTransform);
  });
  const canvasPoint = await page.evaluate(() => {
    const rect = canvas.upperCanvasEl.getBoundingClientRect(), dock = document.querySelector('.rightDock').getBoundingClientRect();
    const x = Math.max(60, Math.min(rect.width, dock.left - rect.left) / 2), y = rect.height / 2;
    canvas.relativePan(new fabric.Point(x - rect.width / 2, 0));
    __denseViewport = JSON.stringify(canvas.viewportTransform);
    return { x: rect.left + x, y: rect.top + y, hittable: document.elementFromPoint(rect.left + x, rect.top + y) === canvas.upperCanvasEl };
  });
  check(canvasPoint.hittable, 'Dense navigation click is covered');
  await page.mouse.dblclick(canvasPoint.x,canvasPoint.y,{delay:85});
  check(await page.evaluate(()=>{
    const o=selectedVinylObjects()[0],entry=layerListRows.get(layerListObjectKey(o));
    const r=entry?.element?.getBoundingClientRect(),p=layerScrollPane().getBoundingClientRect();
    return o?.kloudy.editor_id==='dense-1'&&r&&r.top>=p.top&&r.bottom<=p.bottom
      &&!collapsedLayerGroups.has('dense-group')&&!$('layerSearch').value;
  }),'Canvas double click did not reveal correct virtual row');
  check(await page.evaluate(()=>JSON.stringify(snapshotShapes())===__denseBefore&&editorHistory.index===__denseHistory
    &&JSON.stringify(canvas.viewportTransform)===__denseViewport),'Navigation changed document or viewport');
  check(await page.locator('#layers > li').count()<50,'Navigation devirtualized the layer list');
  await page.screenshot({path:path.join(output,'workflow-dense-navigation.png')});
  await page.evaluate(async()=>{await flushPendingAutosave();await editorSettings.flush?.();});
  if (options.saveBeforeClose) {
    await page.locator('#workspaceFileMenu').click();
    await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill('Workflow close qualification');
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    check(await page.evaluate(() => JSON.stringify(snapshotShapes()) === __denseBefore), 'Save before close changed dense artwork');
  }
  return {paletteSlots:16,emptyAndLocked:true,typingAndIme:true,rebindAndPersistence:true,referenceToggleAndGuidePan:true,
    singleAndGroupCopy:true,extendAndNest:true,dialogAndPointerMembership:true,exactUndoRedo:true,cycleRejected:true,
    nativeArtworkUnchanged:true,projectReopened:true,virtualNavigation:3000};
}
