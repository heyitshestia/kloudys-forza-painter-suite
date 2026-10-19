async (page, options = {}) => {
  const assert=require('node:assert/strict');
  const phase=options.noticePhase||'confirm';
  page.setDefaultTimeout(60000);
  const noTips=async()=>assert.ok(await page.evaluate(()=>['projectSharingDialog','languageNoticeDialog','editorUpdateDialog'].every(id=>!document.getElementById(id).open)));
  const command=async (id,menu='File')=>{
    if (!await page.locator('#'+id).isVisible()) await page.locator('#workspace'+menu+'Menu').click();
    await page.locator('#'+id).click();
  };
  await page.waitForFunction(()=>window.KfpsDesktop?.ready);
  await noTips();
  if (phase==='unconfirmed') {
    assert.equal(await page.locator('#startupHelpDialog').isVisible(),true);
    await page.locator('#startupHelpDontShow').check();
    assert.equal(await page.evaluate(()=>readStartupHelpConfirmed()),false,'Checking without confirming must not acknowledge initial help');
    return {passed:true,initialHelpRetained:true,checkedWithoutConfirmation:true,removedTipsAbsent:true};
  }
  if (await page.locator('#startupHelpDialog').isVisible()) {
    await page.locator('#startupHelpDontShow').check();
    await page.locator('#startupHelpConfirm').click();
  }
  await page.waitForFunction(()=>startupRecoveryHandled);
  if (phase==='restart'||phase==='pending-recovery') {
    const expected=fs.readFileSync(path.join(options.previousOutput,'notice-recovery.json'),'utf8');
    if (await page.locator('#autosaveRecoveryDialog').isVisible()) await page.locator('#recoverAutosave').click();
    await page.waitForFunction(()=>vinylObjects().length===2401&&!recoveryRestoreDepth);
    await noTips();
    assert.equal(await page.evaluate(()=>JSON.stringify(snapshotShapes())),expected);
    assert.equal(await page.evaluate(()=>documentDirty),true);
    if (phase==='restart') await page.evaluate(async()=>{editorSettings.removeItem(EDITOR_UPDATE_ACK_KEY);await KfpsEditorPreferences.flush();});
    else { await command('saveProject');await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty); }
    return {passed:true,phase,recoveredExactly:true,layers:2401,removedNoticeNeverGatesRecovery:true};
  }
  // Absent and stale acknowledgment flags must never gate recovery.
  for (const value of [null,'old-version','modernization-1']) {
    await page.evaluate(async value=>{
      value===null?editorSettings.removeItem(EDITOR_UPDATE_ACK_KEY):editorSettings.setItem(EDITOR_UPDATE_ACK_KEY,value);
      await KfpsEditorPreferences.flush();
    },value);
    await page.reload();await page.waitForFunction(()=>window.KfpsDesktop?.ready&&startupRecoveryHandled);
    await noTips();
    assert.equal(await page.evaluate(()=>editorSettings.getItem(EDITOR_UPDATE_ACK_KEY)),value);
  }
  await page.evaluate(async()=>{
    await loadPayload({shapes:Array.from({length:2400},(_,i)=>({type:1048677,color:[40,180,150,200],
      data:[(i%60)*20-600,Math.floor(i/60)*20-400,.12,.12,i%90,0,0],shape_name:'Recovery fixture '+i}))});
  });
  await command('saveProjectAs');await page.locator('#textPromptInput').fill('Notice removal recovery integration');
  await page.locator('#textPromptInput').press('Enter');await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
  await page.evaluate(()=>{canvas.setActiveObject(vinylObjects()[0]);updateSelectionPanel();});
  await command('duplicateLayer','Edit');await page.waitForFunction(()=>vinylObjects().length===2401&&documentDirty);
  const expected=await page.evaluate(async()=>{
    await flushPendingAutosave();const saved=await readAutosavePayload();
    if(JSON.stringify(saved.shapes)!==JSON.stringify(snapshotShapes()))throw Error('Recovery did not preserve exact fixture');
    return JSON.stringify(snapshotShapes());
  });
  fs.writeFileSync(path.join(output,'notice-recovery.json'),expected);
  return {passed:true,removedTipsAbsent:true,recoveryLayers:2401,
    retired:'Automatic update-tip confirmation/layout/link tests removed with that popup; real 2401-layer recovery and restart phases remain.'};
}
