async (page,options={})=>{
  const h=require(path.join(__dirname,'handmade-project-fixture.cjs'));
  page.setDefaultTimeout(30000);
  const initial=await h.setup(page,output,options),original=await h.snapshot(page),reference=await h.referenceState(page),checks=[];
  const id=JSON.parse(original).at(-1).editor_id;
  const idle=()=>page.waitForFunction(()=>!editorCommands.busy);
  const modes=await page.locator('.toolButton[data-tool-mode]').evaluateAll(nodes=>nodes.map(n=>n.dataset.toolMode));
  for(const mode of modes){await page.locator(`.toolButton[data-tool-mode="${mode}"]`).click();
    h.check(await page.evaluate(mode=>activeToolMode===mode,mode),'Tool rail mode did not activate: '+mode);}
  await page.locator('[data-tool-mode="select"]').click();
  for(let i=0;i<4;i++){
    await page.locator('#toggleRightDock').click();
    h.check(await page.evaluate(()=>document.querySelector('.workspace').classList.contains('dockCollapsed'))===(i%2===0),'Dock toggle disagrees with visible state');
  }
  for(let i=0;i<4;i++){
    await page.locator('#collapseLayersDock').click();
    h.check(await page.evaluate(()=>document.querySelector('.rightDock').classList.contains('layersCollapsed'))===(i%2===0),'Layer collapse state is wrong');
  }
  for(const [i,speed] of Object.keys(h.speeds).entries()){
    const split=await page.locator('#dockSplitter').boundingBox();
    const before=await page.evaluate(()=>document.querySelector('.editorShell').style.getPropertyValue('--editor-layer-height'));
    await h.motion(page,{x:split.x+split.width/2,y:split.y+split.height/2},
      {x:split.x+split.width/2,y:split.y+split.height/2+(i%2?25:-25)},speed);
    h.check(await page.evaluate(()=>document.querySelector('.editorShell').style.getPropertyValue('--editor-layer-height'))!==before,'Splitter movement did not resize the dock');
  }
  h.check(await h.snapshot(page)===original,'Panel resizing changed artwork');
  checks.push('All tool modes','Dock toggle/collapse','Splitter at four speeds');
  await h.selectId(page,id);await page.locator('#quickFitSelected').click();
  h.check(await page.evaluate(()=>Number.isFinite(canvas.getZoom())&&canvas.getZoom()>0),'Quick Fit invalidated viewport');
  await h.type(page,'#nudgeStep','7.5');await page.locator('.upper-canvas').focus();
  const before=await page.evaluate(()=>({left:canvas.getActiveObject().left,top:canvas.getActiveObject().top}));
  await page.keyboard.press('ArrowRight');await page.keyboard.press('Shift+ArrowDown');await page.waitForTimeout(400);
  h.check(await page.evaluate(before=>Math.abs(canvas.getActiveObject().left-before.left-7.5)<1e-7&&Math.abs(canvas.getActiveObject().top-before.top-75)<1e-7,before),'Nudge step or Shift multiplier is wrong');
  const nudged=await h.snapshot(page);
  await page.locator('[data-panel="historyPane"]').click();
  await page.locator('#historyUndo').click();await idle();
  await page.locator('#historyRedo').click();await idle();
  h.check(await h.snapshot(page)===nudged,'History-panel redo differs');
  for(let i=0;i<3&&await h.snapshot(page)!==original;i++){await page.locator('#historyUndo').click();await idle();}
  h.check(await h.snapshot(page)===original,'History-panel undo did not restore artwork');
  checks.push('Quick fit','Fractional nudge and Shift multiplier','History-panel Undo/Redo');
  await page.locator('[data-tool-mode="select"]').click();
  await page.locator('#helpBtn').click();await page.locator('#helpDialog').waitFor({state:'visible'});
  await page.locator('#closeHelp').click();
  await page.evaluate(()=>executeDesktopOperation('open',{mode:'tutorial'}));
  await page.locator('#openShortcutsFromHelp').click();
  await page.locator('#shortcutsDialog').waitFor({state:'visible'});await page.locator('#closeShortcuts').click();
  if(await page.locator('#helpDialog').isVisible())await page.locator('#closeHelp').click();
  if(await page.locator('#startupHelpDialog').isVisible()){
    await page.locator('#startupHelpDontShow').check();await page.locator('#startupHelpConfirm').click();
    await page.locator('#startupHelpDialog').waitFor({state:'hidden'});
  }
  await page.locator('#startEditorTour').click();await page.locator('#editorTourNext').click();
  await page.locator('#editorTourBack').click();
  h.check(await page.evaluate(()=>editorTourState.index===0),'Tour Back missed first step');
  await page.locator('#editorTourSkip').click();
  h.check(await page.evaluate(()=>!editorTourState),'Tour Skip did not close');
  await page.locator('#startEditorTour').click();
  const steps=await page.evaluate(()=>EDITOR_TOUR_STEPS.length);
  for(let i=0;i<steps;i++){
    h.check(await page.evaluate(i=>editorTourState.index===i,i),'Tour skipped a step');
    const card=await page.locator('#editorTourCard').boundingBox();
    h.check(card&&card.x>=0&&card.y>=0&&card.x+card.width<=1601&&card.y+card.height<=1001,'Tour card is outside the native viewport');
    await page.locator('#editorTourNext').click();
  }
  h.check(await page.evaluate(()=>!editorTourState),'Tour Finish did not close');
  checks.push('Help to shortcuts','Tour next/back/skip/finish and on-screen positioning');
  await page.locator('#loadProject').click();await page.locator('#closeProjectBrowser').click();
  await page.locator('#openJsonBrowser').click();
  for(const value of await page.locator('#jsonBrowserSource option').evaluateAll(nodes=>nodes.map(n=>n.value)))await page.locator('#jsonBrowserSource').selectOption(value);
  await page.locator('#closeJsonBrowser').click();
  h.check(await h.snapshot(page)===original,'Browser cancellation changed the document');
  const svg='<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32"><g id="color_1"><rect width="64" height="32" fill="#e02040"/></g><g id="color_2"><rect width="64" height="32" fill="#2040e0"/></g></svg>';
  const filename=path.join(output,'layered-reference.svg');fs.writeFileSync(filename,svg);
  await page.locator('[data-tool-mode="overlay"]').click();await h.fileInput(page,'#overlayInput',filename);
  await page.waitForFunction(()=>editorReference.layered?.layers.length===2);
  const transform=await page.evaluate(()=>JSON.stringify(editorReference.sourceOverlayProjectState().transform));
  await page.locator('#overlaySvgViewMode').selectOption('selected');
  await page.locator('#overlaySvgLayerSelect').selectOption('0');
  await page.waitForFunction(()=>Array.from(editorReference.readOverlayPixel(16,16)).join()==='224,32,64,255');
  await page.locator('#overlaySvgNextLayer').click();
  await page.waitForFunction(()=>Array.from(editorReference.readOverlayPixel(16,16)).join()==='32,64,224,255');
  await page.locator('#overlaySvgPrevLayer').click();
  await page.waitForFunction(()=>Array.from(editorReference.readOverlayPixel(16,16)).join()==='224,32,64,255');
  const svgModes=await page.locator('#overlaySvgViewMode option').evaluateAll(nodes=>nodes.map(n=>n.value));
  for(const mode of svgModes){await page.locator('#overlaySvgViewMode').selectOption(mode);
    await page.waitForFunction(mode=>editorReference.layered.viewMode===mode,mode);
    h.check(await page.evaluate(()=>JSON.stringify(editorReference.sourceOverlayProjectState().transform))===transform,'SVG display mode changed reference transform');}
  h.check(await h.snapshot(page)===original,'Layered reference altered vinyl geometry');
  await h.saveAs(page,'Layered reference UI checkpoint');
  await page.locator('#newCanvas').click();await page.waitForFunction(()=>vinylObjects().length===0);
  await h.openStored(page,path.basename(options.project).replace(/\.fabric-project\.json$/i,''),initial.layers);
  h.check(await h.snapshot(page)===original,'Restoring handmade project lost geometry');
  await page.waitForFunction(()=>editorReference.image?.width===1472);
  h.check(JSON.stringify(await h.referenceState(page))===JSON.stringify(reference),'Restoring handmade project lost original reference metadata');
  checks.push('Project/JSON browser cancel and sources','All SVG display modes','SVG previous/next/select with exact pixel oracle','Original project and reference restored');
  await page.evaluate(()=>flushPendingAutosave());
  await page.locator('#fitView').click();await page.screenshot({path:path.join(output,'handmade-shell.png')});
  return {initial,checks,modes,steps,svgModes,exactArtwork:true,limitations:'Native OS pickers and external folder launch are not physically automated'};
}
