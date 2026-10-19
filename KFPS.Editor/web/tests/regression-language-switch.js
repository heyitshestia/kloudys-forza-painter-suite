async (page, options = {}) => {
  const assert = require('node:assert/strict');
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const initial = options.layers ? await h.setup(page, output, options) : null;
  const results = [];
  page.setDefaultTimeout(20000);
  const ready = () => page.waitForFunction(() => window.KfpsDesktop?.ready && startupRecoveryHandled && !recoveryRestoreDepth);
  const closeDialogs = () => page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(d => d.close()));
  const command = async id => {
    if (!await page.locator('#'+id).isVisible()) await page.locator('#workspaceFileMenu').click();
    await page.locator('#'+id).click();
  };
  const save = async name => {
    await command('saveProjectAs'); await page.locator('#textPromptInput').fill(name);
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  };
  if (initial) await save('Language initial checkpoint');
  // The first-time tip was removed; keep write failures, artwork safety and restart.
  for (const language of (options.languages || ['en','ko','ja'])) {
    await page.evaluate(async language => {
      editorSettings.setItem(KfpsI18n.KEY, language);
      editorSettings.removeItem(LANGUAGE_NOTICE_ACK_KEY);
      await KfpsEditorPreferences.flush();
    }, language);
    await page.reload(); await ready();
    assert.equal(await page.locator('#languageNoticeDialog').isVisible(),false);
    assert.equal(await page.evaluate(()=>KfpsI18n.language),language);
    assert.equal(await page.evaluate(()=>editorSettings.getItem(LANGUAGE_NOTICE_ACK_KEY)),null);
    const layouts=[];
    for (const theme of ['pastel','dark','blackout','whiteout']) {
      await page.evaluate(theme=>editorTheme.applyEditorTheme(theme,{persist:false}),theme);
      for (const size of [{width:1440,height:900},{width:900,height:640}]) {
        await page.setViewportSize(size);
        const measured=await page.locator('#editorLanguageSelect').evaluate(node=>{
          const b=node.getBoundingClientRect();
          return {fits:b.left>=0&&b.right<=innerWidth+1&&b.top>=0&&b.bottom<=innerHeight+1,
            documentFits:document.documentElement.scrollWidth<=innerWidth+1,
            left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:innerWidth,height:innerHeight};
        });
        assert.ok(measured.fits&&measured.documentFits,language+'/'+theme+'/'+size.width+': '+JSON.stringify(measured));
        layouts.push({theme,...size,...measured});
      }
    }
    if (initial) await h.select(page,'Human target');
    else await page.evaluate(async()=>{
      await loadPayload({shapes:[{type:1048677,color:[40,180,150,255],data:[0,0,1,1,0,0,0],
        shape_name:'Save {0} 한국어 日本語',editor_group_id:'g',editor_group_name:'Group {1}'}]});
      canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel();
    });
    const original=await page.evaluate(()=>JSON.stringify(snapshotShapes()));
    const next=language==='en'?'ko':language==='ko'?'ja':'en';
    await page.route('**/api/fabric-editor/preferences',route=>route.request().method()==='POST'
      ?route.fulfill({status:503,contentType:'application/json',body:'{"ok":false,"error":"test: disk unavailable"}'}) :route.continue());
    try {
      await page.locator('#editorLanguageSelect').selectOption(next);
      await page.waitForFunction(()=>!document.querySelector('#editorLanguageSelect').disabled);
      assert.equal(await page.locator('#editorLanguageSelect').inputValue(),language);
      assert.equal(await page.evaluate(()=>editorSettings.getItem(KfpsI18n.KEY)),language);
    } finally { await page.unroute('**/api/fabric-editor/preferences'); }
    await closeDialogs();
    await page.locator('#editorLanguageSelect').selectOption(next);
    await page.waitForFunction(()=>!document.querySelector('#editorLanguageSelect').disabled);
    assert.equal(await page.evaluate(()=>KfpsI18n.language),language,'Unsaved document must not reload on selection');
    assert.equal(await page.evaluate(()=>JSON.stringify(snapshotShapes())),original);
    await closeDialogs();
    await save('Localization '+language+' 한국어 日本語');
    const saved=await page.evaluate(async()=>({name:currentProjectName,
      status:(await fetch(PROJECT_BROWSER_API+'?name='+encodeURIComponent(currentProjectName))).status}));
    assert.equal(saved.status,200);
    await page.evaluate(()=>KfpsEditorPreferences.flush());
    await page.screenshot({path:path.join(output,'language-'+language+'.png')});
    results.push({language,layouts,removedTipAbsent:true,failedWriteRollback:true,safeLanguageSwitch:true,savedProject:saved.name});
  }
  await page.evaluate(async()=>{editorSettings.setItem(KfpsI18n.KEY,'ko');await KfpsEditorPreferences.flush();});
  return {passed:true,initial,results,retired:'First-time language notice checkbox/arrow/acknowledgment tests; this prompt is intentionally no longer shown.'};
}
