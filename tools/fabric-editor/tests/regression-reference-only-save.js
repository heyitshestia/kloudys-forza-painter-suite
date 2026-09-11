async page => {
  page.setDefaultTimeout(12000);
  if (await page.evaluate(()=>vinylObjects().length || currentHistoryState())) {
    throw new Error('This regression requires a fresh, empty native profile');
  }
  const png = await page.evaluate(()=>{
    const fixture = document.createElement('canvas');
    fixture.width=32; fixture.height=48;
    fixture.getContext('2d').fillRect(0,0,32,48);
    return fixture.toDataURL().split(',')[1];
  });
  await page.locator('[data-panel="overlayPane"]').click();
  await page.locator('#overlayInput').setInputFiles({name:'reference-only.png',mimeType:'image/png',buffer:Buffer.from(png,'base64')});
  await page.waitForFunction(()=>overlayImage && documentDirty);
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Reference only save regression');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(()=>!projectSaveInProgress && !documentDirty);
  const before=await page.evaluate(()=>({page:KfpsEditorDiagnostics.snapshot().page,history:currentHistoryState()===savedHistoryState,ref:sourceOverlayProjectState()}));
  if(!before.history) throw new Error('Reference-only project lacks saved history baseline');
  // Reload bypasses the native close handshake, so wait for its recovery write.
  await page.waitForFunction(()=>{
    const r=KfpsEditorDiagnostics.snapshot().recovery;
    return r.pendingRevision>0 && r.serverRevision===r.pendingRevision;
  });
  await page.reload();
  await page.waitForFunction(()=>window.KfpsDesktop?.ready && overlayImage);
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({hasText:'Reference only save regression'}).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(()=>!document.getElementById('projectBrowserDialog').open && !documentDirty);
  const after=await page.evaluate(()=>({page:KfpsEditorDiagnostics.snapshot().page,layers:vinylObjects().length,ref:sourceOverlayProjectState()}));
  if(after.layers!==0 || before.ref.data_url!==after.ref.data_url || before.page===after.page) throw new Error('Reference-only project did not reopen exactly');
  await page.locator('[data-panel="overlayPane"]').click();
  const layerMode=await page.locator('#overlayLayerMode').inputValue();
  await page.locator('#overlayLayerMode').selectOption(layerMode==='above'?'below':'above');
  await page.waitForFunction(()=>documentDirty);
  await page.locator('#saveProject').click();
  await page.waitForFunction(()=>!projectSaveInProgress && !documentDirty);
  return {referenceOnlySave:true,enterConfirmation:true,cleanSavedState:true,realProjectReopen:true,referenceChangeResave:true};
}
