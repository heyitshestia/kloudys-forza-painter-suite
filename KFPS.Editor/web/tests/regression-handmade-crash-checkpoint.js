async(page,options={})=>{
  const h=require(path.join(__dirname,'handmade-project-fixture.cjs'));
  const initial=await h.setupDerived(page,output,{...options,layers:2950});
  await h.selectId(page,'dense-target');await page.locator('#bringFront').click();await h.frameSelection(page);
  const g=await h.geometry(page),r=g.handles.mtr,c=g.center,dx=r.x-c.x,dy=r.y-c.y;
  await h.motion(page,r,{x:c.x+dx*.94-dy*.34,y:c.y+dx*.34+dy*.94},'ordinary');
  const rotated=await h.geometry(page);
  await h.motion(page,rotated.grab,{x:rotated.grab.x+19,y:rotated.grab.y+12},'burst');
  await h.expectTranslation(page,rotated,await h.geometry(page),19,12);
  const accepted=await page.evaluate(()=>contentCommitId),waiting=Date.now();
  await page.waitForFunction(commit=>editorRecovery.status.serverOk&&editorRecovery.status.browserOk&&durableCommitId>=commit,accepted,{timeout:20000});
  const metadata=await page.evaluate(()=>({projectName:currentProjectName,dirty:documentDirty,commit:contentCommitId,durable:durableCommitId}));
  h.check(metadata.dirty,'Crash checkpoint must contain unsaved edits');
  const shapes=await h.snapshot(page);
  const reference=await page.evaluate(()=>JSON.stringify(editorReference.sourceOverlayProjectState()));
  fs.writeFileSync(path.join(output,'crash-shapes.json'),shapes);
  fs.writeFileSync(path.join(output,'crash-expected.json'),JSON.stringify({...metadata,layers:initial.layers,referenceSha256:h.hash(reference),naturalRecoveryMs:Date.now()-waiting}));
  await page.screenshot({path:path.join(output,'before-abrupt-exit.png')});
  return {initial,naturalRecoveryOnly:true,manualSaveInvoked:false,metadata,waitedMs:Date.now()-waiting};
}
