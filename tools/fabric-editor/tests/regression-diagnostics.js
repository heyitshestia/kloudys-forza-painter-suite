async page => {
  await page.waitForFunction(() => window.KfpsEditorDiagnostics?.snapshot().transportOk);
  await page.evaluate(async () => {
    await loadPayload({shapes:[{type:resourceToTypeCode("Primitives",1),data:[0,0,2,2,0,0,0],color:[120,180,210,255]}]});
    fitDesignView();
  });
  await page.locator('[data-panel="performancePane"]').click();
  const before=await page.evaluate(()=>KfpsEditorDiagnostics.snapshot().metrics.totalTasks);
  await page.evaluate(() => new Promise(resolve => setTimeout(() => {
    KfpsEditorDiagnostics.action("rotate");
    const stop=performance.now()+280; while(performance.now()<stop) {}
    KfpsEditorDiagnostics.finish();
    setTimeout(()=>{throw new TypeError("PRIVATE_IMAGE.png PRIVATE_NAME")},0);
    Promise.reject(new RangeError("PRIVATE_TEXT"));
    console.warn("PRIVATE_PATH C:/PRIVATE_FILE.png");
    resolve();
  }, 0)));
  await page.waitForTimeout(2500);
  const snapshot=await page.evaluate(()=>KfpsEditorDiagnostics.snapshot());
  if(snapshot.metrics.totalTasks<=before)throw new Error("Injected stall was not observed");
  const read=()=>JSON.parse(fs.readFileSync(path.join(output,"profile","diagnostics.json"),"utf8"));
  let stored=read();
  if(!stored.recent.some(item=>item.kind==="long-task"&&item.duration>=250&&item.action==="rotate"))throw new Error("Stall duration/action did not reach disk");
  for(const kind of ["js-error","rejection","console-warning"]){if(!stored.recent.some(e=>e.kind===kind))throw new Error(`Missing ${kind} in native diagnostic snapshot`);}
  if(/PRIVATE_/.test(fs.readFileSync(path.join(output,"profile","performance.jsonl"),"utf8")))throw new Error("Private text leaked into diagnostics");
  await page.evaluate(async()=>{await flushPendingAutosave();});
  await page.waitForTimeout(2500);
  stored=read();
  if(!stored.page.recovery.serverRevision||!stored.page.recovery.browserRevision)throw new Error("Recovery acknowledgements missing from diagnostics");
  if(!stored.page.state.editorRevision||!stored.identity.assets["editor.js"])throw new Error("Runtime/install identity missing");
  await page.screenshot({path:path.join(output,"live-performance-en.png")});
  const limits=await page.evaluate(()=>{
    for(let i=0;i<400;i++)KfpsEditorDiagnostics.record("edit");
    const now=KfpsEditorDiagnostics.snapshot();
    return {events:now.events.length,dropped:now.metrics.clientDrops};
  });
  if(limits.events>48||limits.dropped<300)throw new Error("Client event buffer is not bounded");
  return {capturedStall:true,errorsAndWarnings:true,redacted:true,recovery:true,identity:true,limits,logging:stored.logging};
}
