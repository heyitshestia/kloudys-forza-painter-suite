async (page,options={})=> {
  page.setDefaultTimeout(30000);
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const initial=await h.setup(page,output,{...options,layers:2400});
  const trace=await h.monitor(page,output),check=(ok,message)=>{if(!ok)throw Error(message);};
  const idle=()=>page.waitForFunction(()=>!editorAssetLibrary.busy&&!pixelArtGenerationRunning&&!textVinylGenerationRunning&&!editorCommands.busy);
  const prompt=async name=>{await h.type(page,'#textPromptInput',name);await page.locator('#textPromptInput').press('Enter');await page.locator('#textPromptDialog').waitFor({state:'hidden'});};
  const saved=await h.snapshot(page);
  const modes=await page.locator('.toolButton[data-tool-mode]').evaluateAll(nodes=>nodes.map(n=>n.dataset.toolMode));
  try {
    await trace.run('all-tool-modes',async()=> {
      for(const mode of modes) {
        await page.locator(`.toolButton[data-tool-mode="${mode}"]`).click();
        check(await page.evaluate(mode=>activeToolMode===mode,mode),`Tool ${mode} failed`);
      }
    });
    await h.select(page,'Dense batch',true);
    await page.locator('[data-panel="assetsPane"]').click();
    await trace.run('asset-save-48-selected',async()=> {
      await page.locator('#assetSaveSelection').click();await prompt('Dense reusable group');await idle();
      await page.waitForFunction(()=>document.querySelector('.assetPreview img')?.naturalWidth>0);
      check(await page.locator('.editorAsset').count()===1,'Asset was not created');
    });
    const card=page.locator('.editorAsset').first();
    const id=await card.getAttribute('data-asset-id');
    await trace.run('asset-insert-twice',async()=> {
      for(let i=0;i<2;i++){await card.locator('.assetActions > button').first().click();await idle();}
      check(await page.evaluate(count=>vinylObjects().length===count+96&&new Set(vinylObjects().map(o=>o.kloudy.editor_id)).size===count+96,initial.layers),'Asset insert IDs/count differ');
      check(await page.evaluate(count=>JSON.stringify(snapshotShapes().slice(0,count)),initial.layers)===saved,'Asset insert changed source layers');
    });
    const inserted=await h.snapshot(page);
    await trace.run('asset-undo-redo',async()=> {
      await page.locator('#undoBtn').click();await idle();
      check(await page.evaluate(()=>vinylObjects().length)===initial.layers+48,'Asset undo wrong count');
      await page.locator('#redoBtn').click();await idle();
      check(await h.snapshot(page)===inserted,'Asset redo changed exact copies');
    });
    await page.locator('[data-panel="assetsPane"]').click();
    await trace.run('asset-rename-search-cancel-delete',async()=> {
      await card.locator('summary').click();await card.getByRole('button',{name:'Rename',exact:true}).click();
      await prompt('Dense renamed resource');await idle();
      await h.type(page,'#assetSearch','absent resource');check(await page.locator('.editorAsset').count()===0,'Asset filter missed');
      await h.type(page,'#assetSearch','Dense renamed');check(await page.locator('.editorAsset').count()===1,'Renamed asset missing');
      const renamed=page.locator(`[data-asset-id="${id}"]`);
      if(!await renamed.getByRole('button',{name:'Delete',exact:true}).isVisible())await renamed.locator('summary').click();
      await renamed.getByRole('button',{name:'Delete',exact:true}).click();await page.locator('#confirmationDialogCancel').click();
      await idle();
      check(await renamed.count()===1,'Cancelled asset delete removed resource');
      await renamed.locator('summary').click();
      await renamed.getByRole('button',{name:'Delete',exact:true}).click();await page.locator('#confirmationDialogConfirm').click();await idle();
      check(await renamed.count()===0,'Asset delete did not remove resource');
      check(await h.snapshot(page)===inserted,'Deleting saved resource changed artwork');
    });
    await page.locator('[data-tool-mode="text"]').click();
    await h.type(page,'#textVinylInput','KFPS\n0123456789');
    await h.type(page,'#textVinylHeight','100');await page.locator('#textVinylHeight').press('Tab');
    for(const font of ['1','6','11'])await trace.run(`text-font-${font}-replace`,async()=> {
      await page.locator('#textVinylForzaFont').selectOption(font);
      const before=await h.snapshot(page);
      await page.locator('#generateTextVinyl').click();await idle();
      check(await page.evaluate(count=>vinylObjects().length===count+14,initial.layers+96),'Text did not add 14 letters/digits');
      check(await page.evaluate(count=>JSON.stringify(snapshotShapes().slice(0,count)),initial.layers+96)===inserted,'Text changed unrelated dense artwork');
      await h.undo(page,before);await page.locator('[data-tool-mode="text"]').click();
    });
    const pixelFile=path.join(output,'dense-pixel-source.svg');
    fs.writeFileSync(pixelFile,'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32"><rect width="48" height="32" fill="#20a0c0"/><rect x="8" y="8" width="16" height="16" fill="#f0c030"/></svg>');
    await page.locator('[data-tool-mode="pixelArt"]').click();
    await h.fileInput(page,'#pixelArtInput',pixelFile);
    await trace.run('pixel-generate-replace-undo',async()=> {
      await page.locator('#generatePixelArt').click();await idle();
      const first=await h.snapshot(page),count=await page.evaluate(()=>vinylObjects().length);
      check(count>initial.layers+96&&count<=3000,'Pixel art did not add bounded layers');
      await page.locator('#generatePixelArt').click();await idle();
      check(await page.evaluate(()=>vinylObjects().length)===count,'Replace pixel group appended');
      await h.undo(page,first);
      check(await page.evaluate(count=>JSON.stringify(snapshotShapes().slice(0,count)),initial.layers+96)===inserted,'Pixel generation changed unrelated dense artwork');
    });
    await trace.run('help-and-keyboard-favorites',async()=> {
      await page.locator('#helpBtn').click();await page.locator('#helpDialog').waitFor({state:'visible'});await page.locator('#closeHelp').click();
      await page.locator('[data-tool-mode="shapeLibrary"]').click();await page.locator('#shapeFamily').selectOption('Primitives');
      await h.type(page,'#shapeSearch','1048677');
      const before=await h.snapshot(page);
      for(const key of ['Enter','Space','Space']) {
        await page.locator('#shapeGrid .favButton').focus();await page.keyboard.press(key);
      }
      check(await h.snapshot(page)===before,'Favorite shortcut inserted a layer');
      check(await page.evaluate(()=>favorites.has('Primitives:1')),'Favorite not persisted');
    });
    await page.locator('#saveProjectAs').click();await prompt('Dense resource persistence');
    await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
    const expected=await h.snapshot(page);
    await page.evaluate(async()=>{await flushPendingAutosave();await KfpsEditorPreferences.flush();});
    fs.writeFileSync(path.join(output,'dense-resource-expected.json'),expected);
    await page.reload();await page.waitForFunction(()=>window.KfpsDesktop?.ready);
    await page.waitForFunction(count=>vinylObjects().length===count,JSON.parse(expected).length);
    check(await h.snapshot(page)===expected,'Dense resources reload changed artwork');
    check(await page.evaluate(()=>favorites.has('Primitives:1')),'Favorite lost after reload');
    await page.screenshot({path:path.join(output,'dense-resources.png')});
    return {initial,modes,rows:trace.rows,exactReload:true};
  } finally {
    await page.evaluate(()=>{if(window.denseHumanMeasure){denseHumanMeasure.stopped=true;cancelAnimationFrame(denseHumanMeasure.frame);denseHumanMeasure.observer.disconnect();}});
  }
}
