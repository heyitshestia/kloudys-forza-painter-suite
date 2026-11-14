async page => {
  const assert = require('node:assert/strict');
  const checks = [];
  const prepare = async () => page.evaluate(async () => {
    const valid = {type:1048677, data:[75,50,.25,-.5,31,.1,0], color:[220,70,90,255]};
    await loadProjectPayload({name:'Strict Protected UI', shapes:[valid]});
    const object = vinylObjects()[0]; selectObjects([object], 'strict commands fixture');
    await flushPendingAutosave();
    window.__strictBefore = {state: JSON.stringify(snapshotEditorState()), object,
      history:currentHistoryState(), selection:canvas.getActiveObject(), identity:documentIdentity,
      recovery:JSON.stringify(await readAutosavePayload()), association:editorProjects.association};
    recoveryAutosavePayload = {name:'Invalid Recovery', shapes:[{...valid, data:[]}]};
  });
  const retained = () => page.evaluate(async () => {
    await flushPendingAutosave(); const before = window.__strictBefore;
    return {scene:before.state === JSON.stringify(snapshotEditorState()), object:before.object === vinylObjects()[0],
      history:before.history === currentHistoryState(), selection:before.selection === canvas.getActiveObject(),
      identity:before.identity === documentIdentity, recovery:before.recovery === JSON.stringify(await readAutosavePayload()),
      association:before.association === editorProjects.association};
  });
  const check = async label => { const state = await retained(); assert.ok(Object.values(state).every(Boolean), `${label}: ${JSON.stringify(state)}`); checks.push(label); };
  const validForms = await page.evaluate(async () => {
    const forms = [
      {type:1048677, data:[5,6,-.25,.5], color:[1,2,3]},
      {type:1048677, data:[5,6,.25,.5,45]},
      {type:1048677, data:[5,6,.25,.5,45,.1,1,123.456], mask:true, color:[1,2,3,127]},
      {type:1, data:[50,60,120,80], color:[1,2,3,0]},
      {type:2, data:[50,60,-120,80,30], color:[1,2,3]},
      {type:16, data:[50,60,120,80,30], color:[1,2,3,255]},
      {type:8, data:[50,60,120,80,30], color:[1,2,3,255]},
    ];
    for (const shape of forms) {
      await loadProjectPayload({shapes:[shape]});
      if (vinylObjects().length !== 1) throw Error('Valid legacy form dropped');
      const before = JSON.stringify(snapshotShapes());
      await loadProjectPayload({shapes:snapshotShapes()});
      if (before !== JSON.stringify(snapshotShapes())) throw Error('Legacy/native reopen drift');
    }
    await loadProjectPayload({shapes:[]});
    return forms.length;
  });
  await prepare();
  await page.evaluate(async () => {
    await editorProjects.save('Strict Invalid UI', recoveryAutosavePayload, null);
  });
  if (!await page.locator('#loadProject').isVisible()) await page.locator('#workspaceFileMenu').click();
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({has:page.getByText('Strict Invalid UI', {exact:true})}).click();
  await page.locator('#selectProjectEntry').click();
  await page.locator('#messageDialog').waitFor({state:'visible'});
  await check('actual Open Project rejects malformed saved geometry and retains protected document');
  await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(d => d.close()));
  await prepare();
  await page.evaluate(() => document.getElementById('autosaveRecoveryDialog').showModal());
  await page.locator('#recoverAutosave').click();
  await page.waitForFunction(() => document.querySelector('#status')?.textContent.includes('Autosave recovery failed')
    || document.querySelector('#statusText')?.textContent.includes('Autosave recovery failed'));
  await check('actual Recover click rejects malformed geometry without replacing checkpoint');
  await page.evaluate(async () => {
    for (const content of ['null', '{}', '{"shapes":[null]}', '{"shapes":[{"type":1048677,"data":[]}]}']) {
      let rejected = false;
      try { await loadProjectFile(new File([content], 'Invalid.fabric-project.json')); } catch (_) { rejected = true; }
      if (!rejected) throw Error('Malformed file was accepted');
    }
    clearBusy();
  });
  await check('project file parsing rejects null, incomplete and malformed files');
  const result = {passed:true, checks, validLegacyNativeForms:validForms, emptyProject:true};
  fs.writeFileSync(path.join(output, 'strict-geometry-commands.json'), JSON.stringify(result,null,2));
  return result;
}
