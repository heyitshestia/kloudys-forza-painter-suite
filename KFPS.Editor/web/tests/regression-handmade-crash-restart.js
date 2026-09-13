async(page,options={})=>{
  const h=require(path.join(__dirname,'handmade-project-fixture.cjs'));
  const source=options.previousOutput;
  const expected=JSON.parse(fs.readFileSync(path.join(source,'crash-expected.json'),'utf8'));
  await page.waitForFunction(count=>vinylObjects().length===count&&!recoveryRestoreDepth&&!!editorReference.image,expected.layers,{timeout:90000});
  h.check(await h.snapshot(page)===fs.readFileSync(path.join(source,'crash-shapes.json'),'utf8'),'Abrupt-exit recovery changed shapes');
  h.check(h.hash(await page.evaluate(()=>JSON.stringify(editorReference.sourceOverlayProjectState())))===expected.referenceSha256,'Abrupt-exit recovery changed reference bytes or settings');
  h.check(await page.evaluate(()=>currentProjectName)===expected.projectName,'Abrupt-exit recovery lost project association');
  h.check(await page.evaluate(()=>documentDirty),'Recovered unsaved edits were incorrectly marked saved');
  await page.locator('#selectAllLayers').click();
  h.check(await page.evaluate(()=>selectedVinylObjects().length)===expected.layers,'Recovered canvas controls did not respond');
  await page.locator('#clearLayerSelection').click();
  await h.saveAs(page,'Recovered after abrupt exit');
  h.check(await h.snapshot(page)===fs.readFileSync(path.join(source,'crash-shapes.json'),'utf8'),'Saving recovered work changed its shapes');
  await page.locator('#fitView').click();await page.screenshot({path:path.join(output,'after-abrupt-restart.png')});
  return {layers:expected.layers,exactShapes:true,exactReferenceBytesAndState:true,automaticRecovery:true,unsavedStatusPreserved:true,controlsAndSaveWork:true};
}
