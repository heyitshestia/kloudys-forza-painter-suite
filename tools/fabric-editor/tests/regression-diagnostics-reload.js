async page => {
  page.setDefaultTimeout(20000);
  await page.waitForFunction(()=>KfpsEditorDiagnostics.snapshot().transportOk);
  const initial=await page.evaluate(async()=>{
    await loadPayload({shapes:[{type:resourceToTypeCode('Primitives',1),data:[0,0,2,2,0,0,0],color:[70,140,220,255]}]});
    fitDesignView();await flushPendingAutosave();
    return KfpsEditorDiagnostics.snapshot().page;
  });
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Diagnostic reload fixture');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(()=>!projectSaveInProgress && !documentDirty);
  await page.locator('#editorLanguageSelect').selectOption('ko');
  await page.waitForFunction(()=>!document.getElementById('editorLanguageSelect').disabled);
  await page.locator('#messageDialogClose').click();
  await page.reload();
  await page.waitForFunction(()=>window.KfpsDesktop?.ready && KfpsEditorDiagnostics.snapshot().transportOk);
  const after=await page.evaluate(()=>({page:KfpsEditorDiagnostics.snapshot().page,language:KfpsI18n.language,layers:vinylObjects().length}));
  if(after.page===initial||after.language!=='ko'||after.layers!==1)throw new Error('Reload lost identity, language or recovered artwork: '+JSON.stringify(after));
  await page.locator('[data-panel="performancePane"]').click();
  await page.waitForTimeout(2200);
  const content=await page.locator('#performancePane').innerText();
  if(!content.includes('\uc2e4\uc2dc\uac04 \uc131\ub2a5')||!content.includes('\ub85c\uceec\uc5d0 \uae30\ub85d \uc911'))throw new Error('Korean performance readout incomplete');
  const bounds=await page.locator('#performancePane').evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth}));
  if(bounds.scroll>bounds.width+1)throw new Error('Performance panel overflows');
  await page.screenshot({path:path.join(output,'live-performance-ko.png')});
  const records=fs.readFileSync(path.join(output,'profile','performance.jsonl'),'utf8').trim().split('\n').map(line=>JSON.parse(line));
  if(!records.some(r=>r.page===initial)||!records.some(r=>r.page===after.page))throw new Error('Diagnostic page history did not survive reload');
  return {savedReload:true,recoveredLayers:after.layers,korean:true,pageHistoryRetained:true};
}
