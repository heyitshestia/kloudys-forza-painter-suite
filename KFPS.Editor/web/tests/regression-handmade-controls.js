async (page,options={})=>{
  const h=require(path.join(__dirname,'handmade-project-fixture.cjs'));
  page.setDefaultTimeout(30000);
  const initial=await h.setupDerived(page,output,{...options,layers:2400});
  const check=h.check,checks=[],rows=[];
  const measure=async(name,action)=>{const trace=await h.monitor(page,output);try{await trace.run(name,action);rows.push(...trace.rows);}finally{await trace.close();}};
  const idle=()=>page.waitForFunction(()=>!editorCommands.busy&&!editorAssetLibrary.busy&&!pixelArtGenerationRunning);
  await h.saveAs(page,'Control coverage checkpoint');
  const original=await h.snapshot(page);

  await h.selectId(page,'dense-target');
  await page.locator('[data-panel="propertiesPane"]').click();
  await page.locator('#opacitySlider').focus();await page.keyboard.press('Home');
  for(let i=0;i<80;i++)await page.keyboard.press('ArrowRight');
  await page.locator('#opacitySlider').press('Tab');
  check(await page.evaluate(()=>objectToShape(selectedVinylObjects()[0]).color[3])===80,'Keyboard alpha adjustment failed');
  await page.locator('#layerSearch').fill('Human');
  await page.locator('.layerRow').filter({hasText:'Human alternate'}).click({modifiers:['Control']});
  check(await page.evaluate(()=>selectedVinylObjects().length)===2,'Alpha test did not select two layers');
  const beforeAlpha=await h.snapshot(page);
  const alpha=await page.evaluate(()=>objectToShape(unlockedObjects(selectedVinylObjects())[0]).color[3]);
  await page.locator('#equalizeAlpha').click();await idle();
  check(await page.evaluate(alpha=>selectedVinylObjects().every(o=>objectToShape(o).color[3]===alpha),alpha),'Equalize Alpha failed');
  await h.undo(page,beforeAlpha);checks.push('keyboard alpha and two-layer equalize/undo');
  for(const id of ['colorSwatchButton','colorPanelSwatch','quickColorSwatch']){
    await page.locator('#'+id).click();await page.locator('#colorDialog').waitFor({state:'visible'});
    await page.locator('#closeColorDialog').click();
  }
  checks.push('all three saved-color entry buttons');
  await h.saveAs(page,'Control alpha checkpoint');

  const assetFile=path.join(output,'shared.kfps-asset.json');
  const sourceShapes=JSON.parse(await h.snapshot(page)).slice(0,24);
  fs.writeFileSync(assetFile,JSON.stringify({format:'kfps_editor_asset_v1',name:'Shared handmade subset',shapes:sourceShapes}));
  await page.locator('[data-panel="assetsPane"]').click();
  await h.fileInput(page,'#assetInput',assetFile);await idle();
  await page.waitForFunction(()=>document.querySelectorAll('.editorAsset').length===1);
  await page.locator('#assetRefresh').click();await idle();
  const beforeAsset=await h.snapshot(page);
  await page.locator('.editorAsset .assetPreview').click();await idle();
  check(await page.evaluate(()=>vinylObjects().length)===2424,'Imported asset did not insert all 24 layers');
  check(await page.evaluate(()=>JSON.stringify(snapshotShapes().slice(0,2400)))===beforeAsset,'Asset insertion altered source artwork');
  const inserted=JSON.parse(await h.snapshot(page)).slice(2400);
  const offset=[inserted[0].data[0]-sourceShapes[0].data[0],inserted[0].data[1]-sourceShapes[0].data[1]];
  check(inserted.every((shape,i)=>shape.type===sourceShapes[i].type&&JSON.stringify(shape.color)===JSON.stringify(sourceShapes[i].color)
    &&shape.data.every((value,j)=>Math.abs(value-sourceShapes[i].data[j]-(j<2?offset[j]:0))<1e-6)),
  'Asset import changed shapes beyond its documented placement translation');
  await h.undo(page,beforeAsset);
  const invalid=path.join(output,'not-an-asset.json');fs.writeFileSync(invalid,JSON.stringify({format:'wrong',shapes:sourceShapes}));
  await h.fileInput(page,'#assetInput',invalid);await idle();
  check(await page.locator('#assetStatus').getAttribute('class').then(v=>(v||'').includes('assetError')),'Invalid asset lacked an error');
  check(await page.locator('.editorAsset').count()===1&&await h.snapshot(page)===beforeAsset,'Invalid asset changed the library or canvas');
  await page.locator('#assetRefresh').click();await idle();
  checks.push('asset import/refresh/preview insert/exact undo/invalid import');

  await page.locator('[data-tool-mode="shapeLibrary"]').click();
  await page.locator('#shapeSearch').fill('');
  const fontFamily=await page.locator('#shapeFamily option').evaluateAll(items=>items.find(item=>item.value.includes('Letters'))?.value);
  check(fontFamily,'Native letter family missing');
  await page.locator('#shapeFamily').selectOption(fontFamily);
  await page.locator('#showFavorites').click();
  await page.locator('#showAllShapes').click();
  check(await page.evaluate(()=>!showFavoritesOnly),'All did not leave favorites-only mode');
  await page.locator('#reuseLastFontSize').check();
  await page.locator('#shapeGrid .shapeTile').nth(0).locator('.shapeName').click();await idle();
  await page.locator('[data-panel="propertiesPane"]').click();
  for(const [id,value] of [['sxInput','0.71'],['syInput','0.49'],['rotInput','17'],['skewInput','6']]){
    await h.type(page,'#'+id,value);await page.locator('#'+id).press('Enter');
  }
  await page.locator('#applyFields').click();
  const remembered=await page.evaluate(()=>{
    const o=selectedVinylObjects()[0];
    const expected=Object.fromEntries(['scaleX','scaleY','angle','skewX'].map(key=>[key,o[key]]));
    if(!lastFontShapeTransform||Object.keys(expected).some(key=>Math.abs(lastFontShapeTransform[key]-expected[key])>1e-9))throw Error('Typed font transform was not remembered');
    return expected;
  });
  await page.locator('[data-tool-mode="shapeLibrary"]').click();
  await page.locator('#shapeGrid .shapeTile').nth(1).locator('.shapeName').click();await idle();
  check(await page.evaluate(expected=>{
    const o=selectedVinylObjects()[0];return ['scaleX','scaleY','angle','skewX'].every(key=>Math.abs(o[key]-expected[key])<1e-9);
  },remembered),'New font shape did not reuse the saved transform');
  await page.locator('[data-panel="propertiesPane"]').click();
  const fontBefore=await h.snapshot(page);
  const rememberedBefore=await page.evaluate(()=>JSON.stringify(lastFontShapeTransform));
  const label=await page.locator('[data-numeric-for="sxInput"]').boundingBox();
  const from={x:label.x+label.width/2,y:label.y+label.height/2};
  await page.mouse.move(from.x,from.y);await page.mouse.down();await page.mouse.move(from.x+20,from.y,{steps:12});
  check(await h.snapshot(page)!==fontBefore,'Font numeric drag did not preview');
  check(await page.evaluate(()=>JSON.stringify(lastFontShapeTransform))===rememberedBefore,'Uncommitted font preview changed the preference');
  await page.keyboard.press('Escape');await page.mouse.up();
  check(await h.snapshot(page)===fontBefore&&await page.evaluate(()=>JSON.stringify(lastFontShapeTransform))===rememberedBefore,'Cancelled font preview changed artwork or preference');
  await h.motion(page,from,{x:from.x+20,y:from.y},'ordinary');
  check(await page.evaluate(()=>Math.abs(lastFontShapeTransform.scaleX-selectedVinylObjects()[0].scaleX)<1e-9),'Committed numeric-label drag did not remember font size');
  await page.locator('[data-tool-mode="shapeLibrary"]').click();
  await page.locator('#reuseLastFontSize').uncheck();
  check(await page.evaluate(()=>!reuseLastFontSize),'Font reuse did not turn off');
  checks.push('favorite/all filter and font-size reuse on/off with applied transforms');
  await h.saveAs(page,'Control font checkpoint');

  const pixelFile=path.join(output,'alpha-pixel-source.svg');
  fs.writeFileSync(pixelFile,'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><rect width="8" height="16" fill="#20a0c0"/><rect x="8" width="8" height="16" fill="#e03090" opacity="0.35"/></svg>');
  await page.locator('[data-tool-mode="pixelArt"]').click();
  await h.fileInput(page,'#pixelArtInput',pixelFile);
  for(const [alphaCutoff,tolerance] of [[0,0],[128,24],[255,80]]){
    const beforePixel=await h.snapshot(page);
    await h.type(page,'#pixelArtAlphaCutoff',alphaCutoff);await page.locator('#pixelArtAlphaCutoff').press('Tab');
    await h.type(page,'#pixelArtTolerance',tolerance);await page.locator('#pixelArtTolerance').press('Tab');
    await page.locator('#generatePixelArt').click();await idle();
    check(await page.evaluate(()=>vinylObjects().length>2402&&vinylObjects().length<=3000),'Pixel settings did not produce bounded artwork');
    if(alphaCutoff===255)check(await h.snapshot(page)===beforePixel&&(await page.locator('#pixelArtStatus').textContent()).includes('No visible'),'Fully filtered pixel generation changed previous artwork');
    check(await page.locator('#pixelArtGridW').getAttribute('readonly')!==null&&await page.locator('#pixelArtGridH').getAttribute('readonly')!==null,'Detected grid fields should remain read-only');
  }
  checks.push('pixel alpha/tolerance endpoint combinations and detected-grid fields');
  await h.saveAs(page,'Control export checkpoint');
  const portableExpected=await page.evaluate(()=>JSON.stringify(snapshotShapes().map(shape=>({type:shape.type,color:shape.color,data:shape.data}))));
  const expectedCount=await page.evaluate(()=>vinylObjects().length);
  await page.locator('#exportJson').click();await page.waitForFunction(()=>!exportSaveInProgress);
  const exported=await page.evaluate(()=>selectedJsonBrowserEntry());check(exported?.id,'No export browser entry');
  await page.locator('#newCanvas').click();await page.waitForFunction(()=>vinylObjects().length===0&&!recoveryRestoreDepth);
  await page.locator('#openJsonBrowser').click();
  await page.waitForFunction(()=>document.querySelectorAll('.jsonBrowserEntry').length>0);
  await page.locator('.jsonBrowserEntry').filter({hasText:exported.name}).first().click();
  await page.locator('#selectJsonBrowserEntry').click();
  await page.waitForFunction(count=>vinylObjects().length===count&&!recoveryRestoreDepth,expectedCount);
  check(await page.evaluate(()=>JSON.stringify(snapshotShapes().map(shape=>({type:shape.type,color:shape.color,data:shape.data}))))===portableExpected,'Actual JSON-browser import changed exported shape data');
  checks.push('export to JSON browser, New, select exported entry and exact portable import');
  await h.saveAs(page,'Control JSON import checkpoint');
  await h.openStored(page,'Control coverage checkpoint',initial.layers);
  check(await h.snapshot(page)===original,'Control workflows failed to reopen untouched initial derivative');
  await measure('help-open-close',async()=>{await page.locator('#helpBtn').click();await page.locator('#closeHelp').click();});
  await measure('shape-library-open',async()=>{await page.locator('[data-tool-mode="shapeLibrary"]').click();});
  await measure('shape-search-full-type',async()=>{await page.locator('#shapeFamily').selectOption('Primitives');await h.type(page,'#shapeSearch','1048677');});
  await measure('shape-favorite-three-toggles',async()=>{
    for(const key of ['Enter','Space','Space']){await page.locator('#shapeGrid .favButton').focus();await page.keyboard.press(key);}
  });
  await page.screenshot({path:path.join(output,'controls-final.png')});
  return {initial,checks,rows,exactOriginalReopen:true,fileSelection:'CDP input selection; physical OS picker remains outside this suite'};
}
