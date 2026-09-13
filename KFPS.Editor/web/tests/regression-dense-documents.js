async (page,options={})=> {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  page.setDefaultTimeout(30000);
  const initial=await h.setup(page,output,{...options,layers:2900});
  const trace=await h.monitor(page,output);
  const check=(ok,message)=>{if(!ok)throw Error(message);};
  const prompt=async(selector,name)=> {
    await page.locator(selector).click();await h.type(page,'#textPromptInput',name);
    await page.locator('#textPromptInput').press('Enter');
    await page.locator('#textPromptDialog').waitFor({state:'hidden'});
  };
  const saveIdle=()=>page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
  const open=async name=> {
    await page.locator('#loadProject').click();
    await page.locator('.projectBrowserEntry').filter({has:page.getByText(name,{exact:true})}).click();
    await page.locator('#selectProjectEntry').click();
    await page.waitForFunction(count=>vinylObjects().length===count&&!recoveryRestoreDepth,initial.layers);
    if(initial.reference)await page.waitForFunction(({dimensions,opacity})=>!documentDirty
      &&editorReference.image?.width===dimensions[0]&&editorReference.image?.height===dimensions[1]
      &&Number(document.getElementById('overlayOpacity').value)===opacity,
    {dimensions:initial.reference,opacity:initial.referenceOpacity});
  };
  try {
    for(const order of ['below','above']) {
      if(initial.reference) {
        await page.locator('[data-tool-mode="overlay"]').click();
        await page.locator('#overlayLayerMode').selectOption(order);
      }
      await h.select(page,'Human target');
      await trace.run(`${order}/rename-layer`,async()=> {
        await prompt('#renameSelectedLayer','Document target');
        check(await page.evaluate(()=>selectedVinylObjects()[0].kloudy.name)==='Document target','Rename failed');
        await prompt('#renameSelectedLayer','Human target');
      });
      await h.select(page,'Dense batch',true);
      await trace.run(`${order}/rename-group`,async()=> {
        await prompt('#renameSelectedGroup','Document group');
        check(await page.evaluate(()=>selectedGroupMembers().every(o=>o.kloudy.group_name==='Document group')),'Group rename failed');
        await prompt('#renameSelectedGroup','Dense batch');
      });
      const expected=await h.snapshot(page),name=`Dense documents ${order}`;
      await trace.run(`${order}/save-as`,async()=> {await prompt('#saveProjectAs',name);await saveIdle();});
      await trace.run(`${order}/save-existing`,async()=> {await page.locator('#saveProject').click();await saveIdle();});
      await trace.run(`${order}/export-flat`,async()=> {
        await page.locator('#exportJson').click();await page.waitForFunction(()=>!exportSaveInProgress);
      });
      check(await page.evaluate(async count=> {
        const entry=selectedJsonBrowserEntry();
        if(!entry)return false;
        const {payload}=await (await fetch(`${JSON_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json();
        return payload.shapes.length===count&&payload.shapes.every(shape=>Object.keys(shape).every(key=>!key.startsWith('editor_')));
      },initial.layers),'Dense flat export is missing layers or includes editor-only groups');
      await trace.run(`${order}/new-canvas`,async()=> {
        await page.locator('#newCanvas').click();await page.waitForFunction(()=>vinylObjects().length===0&&!recoveryRestoreDepth);
      });
      await trace.run(`${order}/open-project`,async()=> {await open(name);});
      check(await h.snapshot(page)===expected,'Project reopen changed exact shapes/groups');
      check(await page.evaluate(()=>currentProjectName)===name,'Reopen lost project name');
      if(initial.reference)check(await page.evaluate(()=>!!editorReference.image),'Reopen lost reference');
      await trace.run(`${order}/fit-view`,async()=>{await page.locator('#fitView').click();});
      await trace.run(`${order}/explicit-recovery`,async()=> {
        await page.evaluate(async()=>{await flushPendingAutosave();});
      });
      check(await page.evaluate(async()=>JSON.stringify((await readAutosavePayload()).shapes))===expected,'Recovery differs from reopened project');
      await page.screenshot({path:path.join(output,`dense-documents-${order}.png`)});
    }
    return {initial,rows:trace.rows,exactReopenAndRecovery:true};
  } finally {await trace.close();}
}
