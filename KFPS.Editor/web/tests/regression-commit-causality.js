async page => {
  const assert = require('node:assert/strict');
  const cp = require('node:child_process');
  const {pathToFileURL} = require('node:url');
  const root = path.resolve(__dirname, '../../..');
  const {normalizeEditor} = await import(pathToFileURL(path.join(root,'tools/support_worker/public/editor-diagnostics.mjs')));
  await page.evaluate(async () => {
    await loadPayload({shapes:[...Array.from({length:2799},(_,i)=>({type:1048677,
      data:[-720+i%60*24,-550+Math.floor(i/60)*24,.10,.10,0,0,0],color:[90,130,180,255]})),
      {type:editorCatalog.resourceToTypeCode('Primitives',27),data:[0,0,2,2,0,0,0],color:[215,90,120,255]}]});
    const image=document.createElement('canvas');image.width=5888;image.height=2816;
    const ctx=image.getContext('2d');ctx.fillStyle='#607582';ctx.fillRect(0,0,image.width,image.height);
    await editorReference.loadOverlayImageFromUrl(image.toDataURL(),'PRIVATE_REFERENCE.png');image.width=image.height=1;
    editorReference.image.set({opacity:.6});setOverlayLayerMode('below');
    window.causalTarget=vinylObjects().at(-1);
    selectObjects([causalTarget],'test');activateDockPanel('propertiesPane');
    canvas.setViewportTransform([1,0,0,1,canvas.width/2,canvas.height/2]);
    await flushPendingAutosave();await KfpsEditorDiagnostics.flush();
  });
  const rows=[];
  const supportRoot=path.join(output,'support-collection');
  fs.mkdirSync(path.join(supportRoot,'runtime/fabric-editor'),{recursive:true});
  async function capture(action, before) {
    const cause=await page.evaluate(async () => {
      await flushPendingAutosave();
      const payload=await readAutosavePayload();
      if(JSON.stringify(payload.shapes)!==JSON.stringify(snapshotShapes()))throw Error('Recovery contents mismatch');
      return payload.editor_recovery_cause;
    });
    assert.ok(cause.commitId>before,`${action} was not accepted`);
    await page.waitForTimeout(300);
    await page.evaluate(()=>KfpsEditorDiagnostics.flush());
    await page.waitForTimeout(350);
    const snapshot=JSON.parse(fs.readFileSync(path.join(output,'profile/diagnostics.json'),'utf8'));
    fs.writeFileSync(path.join(supportRoot,'runtime/fabric-editor/diagnostics.json'),JSON.stringify(snapshot));
    const python=process.env.KFPS_TEST_PYTHON || path.join(process.env.KFPS_TEST_APP_ROOT,'python/python.exe');
    const script="import json,sys,time;from pathlib import Path;sys.path[:0]=[str(Path.cwd()),str(Path.cwd()/'KFPS.UI/src')];from kfps_ui.support_report import build_support_report;print(json.dumps(build_support_report(Path(sys.argv[1]), {'page':'editor'}, since=time.time()-60, collect=lambda:{})))";
    const report=JSON.parse(cp.execFileSync(python,['-B','-c',script,supportRoot],{cwd:root,encoding:'utf8',windowsHide:true}));
    const editor=normalizeEditor(report.technical.editor);
    fs.writeFileSync(path.join(output,`${action}-support.json`),JSON.stringify(editor,null,2));
    const events=[...(editor.page.events||[]),...editor.recent];
    const matching=events.filter(e=>e.commitId===cause.commitId&&e.pageId===cause.pageId&&e.documentId===cause.documentId);
    for(const kind of ['commit','checkpoint','recovery-result'])assert.ok(matching.some(e=>e.kind===kind),`${action} missing ${kind} in support artifact`);
    assert.ok(matching.some(e=>e.kind==='checkpoint'&&e.source==='native'&&e.state==='committed'),`${action} missing actual native disk acknowledgment`);
    assert.ok(matching.some(e=>e.kind==='recovery-result'&&e.serverOk),`${action} missing durable result`);
    if(action!=='coalesced')assert.ok(matching.some(e=>e.kind==='commit'&&e.action===action),`${action} incorrectly classified`);
    if(action==='move') {
      assert.ok(cause.inputId>0,'Real pointer gesture lacks an input identity');
      assert.ok(events.some(e=>e.kind==='edit'&&e.inputId===cause.inputId),'Pointer edit cannot be linked to accepted content');
    }
    assert.equal(JSON.stringify(editor).includes('PRIVATE'),false);
    rows.push({action,...cause,events:matching});
    return cause;
  }
  let before=await page.evaluate(()=>contentCommitId);
  await page.locator('#duplicateLayer').click();
  await page.waitForFunction(()=>vinylObjects().length===2801&&!editorCommands.pending);
  const duplicate=await capture('duplicate',before);assert.ok(duplicate.commandId>0);
  before=duplicate.commitId;
  await page.locator('#rotInput').fill('33');await page.locator('#rotInput').press('Enter');
  await capture('numeric',before);
  // Find a painted point on the selected quarter circle; drive the normal pointer path.
  const grab=await page.evaluate(()=>{
    const o=canvas.getActiveObject(),rect=canvas.upperCanvasEl.getBoundingClientRect();
    for(const [x,y] of [[0,0],[-.2,-.2],[.2,-.2],[-.2,.2],[.2,.2]]){
      const world=fabric.util.transformPoint(new fabric.Point(x*o.width,y*o.height),o.calcTransformMatrix());
      if(KfpsFabricAdapter.visiblePixelAt(canvas,o,world)){const p=fabric.util.transformPoint(world,canvas.viewportTransform);return{x:p.x+rect.left,y:p.y+rect.top};}
    }throw Error('No painted drag point');
  });
  before=await page.evaluate(()=>contentCommitId);
  await page.mouse.move(grab.x,grab.y);await page.mouse.down();
  await page.mouse.move(grab.x+24,grab.y+14,{steps:16});await page.mouse.up();
  await capture('move',before);
  await page.evaluate(()=>{window.causalNoop=contentCommitId;pushHistory('field edit');if(contentCommitId!==causalNoop)throw Error('No-op acquired a commit ID');});
  const worker=page.workers().find(w=>w.url().includes('editor-persistence-worker'));
  if(!worker)throw Error('Persistence worker not attached');
  await worker.evaluate(()=>{self.causalFetch=fetch;self.fetch=(url,options)=>String(url).includes('/autosave')&&options?.method==='POST'
    ?Promise.resolve(new Response(JSON.stringify({error:'PRIVATE failure',code:'http_error'}),{status:503})):causalFetch(url,options);});
  let failure;
  try {
    await page.locator('#xInput').fill('47');await page.locator('#xInput').press('Enter');
    await page.evaluate(()=>flushPendingAutosave());
    failure=await page.evaluate(()=>({status:editorRecovery.status,cause:currentRecoveryCause(),events:KfpsEditorDiagnostics.snapshot().events}));
    assert.equal(failure.status.serverOk,false);assert.equal(failure.status.browserOk,true);assert.equal(failure.status.code,'http_error');
    assert.ok(failure.events.some(e=>e.kind==='recovery-result'&&e.commitId===failure.cause.commitId&&e.errorCode==='http_error'&&!e.serverOk));
    await page.waitForTimeout(300);await page.evaluate(()=>KfpsEditorDiagnostics.flush());
  } finally {await worker.evaluate(()=>{self.fetch=causalFetch;});}
  await page.waitForFunction(()=>editorRecovery.status.serverOk===true,null,{timeout:10000});
  await capture('numeric',failure.cause.commitId-1);
  before=await page.evaluate(()=>contentCommitId);
  await page.evaluate(()=>{
    const old=KfpsEditorDiagnostics.record;KfpsEditorDiagnostics.record=()=>{throw Error('PRIVATE observer failure');};
    try {for(let i=0;i<3;i++){canvas.getActiveObject().left+=1;pushHistory('field edit',{changedObjects:[canvas.getActiveObject()]});}}
    finally{KfpsEditorDiagnostics.record=old;}
  });
  // Observer faults must not roll back edits, and the latest checkpoint covers their range.
  await page.evaluate(()=>{canvas.getActiveObject().left+=1;pushHistory('field edit',{changedObjects:[canvas.getActiveObject()]});});
  const coalesced=await capture('coalesced',before);
  assert.ok(coalesced.firstCommitId<=before+1);
  await page.evaluate(()=>{for(let i=0;i<1200;i++)KfpsEditorDiagnostics.record('commit',{state:'committed'});});
  const drops=await page.evaluate(()=>KfpsEditorDiagnostics.snapshot().metrics.criticalDrops);assert.ok(drops>0);
  return {passed:true,layers:2801,reference:[5888,2816],rows,browserFallback:true,retry:true,observerFailureIsolated:true,noOp:true,criticalDrops:drops};
}
