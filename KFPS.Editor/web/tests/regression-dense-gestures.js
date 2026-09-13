async (page,options={})=> {
  page.setDefaultTimeout(15000);
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const initial=await h.setup(page,output,{...options,layers:2950});
  const trace=await h.monitor(page,output);
  const check=(ok,message)=>{if(!ok)throw Error(message);};
  if (options.primeHistory) {
    await h.select(page, 'Human target');
    await page.locator('.upper-canvas').focus();
    for (let index = 0; index < 85; index++) {
      await page.keyboard.press(index % 2 ? 'ArrowLeft' : 'ArrowRight');
      await page.waitForTimeout(450);
    }
    const entries = await page.evaluate(() => editorHistory.entries.length);
    check(entries === 80, 'Actual keyboard edits did not fill the 80-entry history');
    fs.writeFileSync(path.join(output, 'history-primed.json'), JSON.stringify({ entries, actualKeyboardEdits: 85, noForcedGc: true }));
  }
  const samples=[];
  const targetTypes=options.types || [1048706,1048677,1048678,1048712,1048715];
  const cycles=Number(options.cycles || 4);
  const started=Date.now(),minimumSeconds=Number(options.minimumSeconds||0);
  if(!Number.isFinite(minimumSeconds)||minimumSeconds<0||minimumSeconds>1800)throw Error('Invalid gesture duration');
  const checkpoints=[];
  let nextCheckpoint=0,round=0;
  try {
    do {
    shapeCases: for(const order of ['below','above'])for(const type of targetTypes) {
      if(initial.reference) {
        await page.locator('[data-tool-mode="overlay"]').click();
        await page.locator('#overlayLayerMode').selectOption(order);
      }
      await h.select(page,'Human target');
      const beforeReplace=await h.snapshot(page);
      await page.locator('#shapePlacementMode').selectOption('replace');
      await page.locator('[data-tool-mode="shapeLibrary"]').click();
      await page.locator('#shapeFamily').selectOption('Primitives');
      await h.type(page,'#shapeSearch',String(type));
      await page.locator('#shapeGrid .shapeTile img').first().click();
      await page.waitForFunction(type=>selectedVinylObjects().length===1&&objectToShape(selectedVinylObjects()[0]).type===type,type);
      const targetName=await page.evaluate(()=>selectedVinylObjects()[0].kloudy.name);
      const targetId=await page.evaluate(()=>selectedVinylObjects()[0].kloudy.editor_id);
      check(await page.locator('#shapePlacementMode').inputValue()==='top','Replace once did not return to normal placement');
      check(await page.evaluate(()=>vinylObjects().length)===initial.layers,'Replace once changed dense layer count');
      await page.locator('[data-tool-mode="select"]').click();
      await page.locator('#fitView').click();
      if(options.project)await require(path.join(__dirname,'handmade-project-fixture.cjs')).frameSelection(page);
      for(let cycle=0;cycle<cycles;cycle++) {
        const before=await h.snapshot(page);
        await trace.run(`${round}/${order}/${type}/${cycle}/rotate-move-wheel-move-scale-skew`,async()=> {
          const first=await h.geometry(page),r=first.handles.mtr,c=first.center;
          const dx=r.x-c.x,dy=r.y-c.y,turn=cycle%2?-.4:.4;
          await page.mouse.move(r.x,r.y);await page.mouse.down();
          for(let step=1;step<=12;step++) {
            const a=turn*step/12;
            await page.mouse.move(c.x+dx*Math.cos(a)-dy*Math.sin(a),c.y+dx*Math.sin(a)+dy*Math.cos(a));
          }
          await page.mouse.up();
          const rotated=await h.geometry(page);
          check(Math.abs(rotated.angle-first.angle)>5,'Pointer rotation did not change angle');
          await h.drag(page,rotated.grab,{x:rotated.grab.x+17,y:rotated.grab.y+9});
          const moved=await h.geometry(page);
          check(Math.hypot(moved.left-rotated.left,moved.top-rotated.top)>.1,'Immediate movement after rotation did nothing');
          await page.mouse.move(moved.center.x,moved.center.y);
          for(const delta of [-160,160,-160,160])await page.mouse.wheel(0,delta);
          const zoomed=await h.geometry(page);
          await h.drag(page,zoomed.grab,{x:zoomed.grab.x-17,y:zoomed.grab.y-9});
          const beforeResize=await h.geometry(page),handle=beforeResize.handles[cycle%2?'br':'mr'];
          await h.drag(page,handle,{x:handle.x+9,y:handle.y+4},cycle%2?['Control']:[]);
          const resized=await h.geometry(page);
          check(Math.abs(resized.scaleX-beforeResize.scaleX)+Math.abs(resized.scaleY-beforeResize.scaleY)>1e-5,'Resize did not change scales');
          const corner=resized.handles.br;
          await h.drag(page,corner,{x:corner.x+9,y:corner.y-5},['Shift']);
          const skewed=await h.geometry(page);
          check(Math.abs(skewed.skewX-resized.skewX)+Math.abs(skewed.skewY-resized.skewY)>.01,'Shift corner drag did not skew');
          samples.push({order,type,cycle,rotate:true,immediateMove:true,wheelMove:true,scale:true,shiftSkew:true});
          for(let undo=0;undo<8&&await h.snapshot(page)!==before;undo++) {
            await page.locator('#undoBtn').click();await page.waitForFunction(()=>!editorCommands.busy);
          }
          check(await h.snapshot(page)===before,'Rapid gesture chain failed exact undo');
          if(options.project)await require(path.join(__dirname,'handmade-project-fixture.cjs')).selectId(page,targetId);
          else await h.select(page,targetName);
        });
        if(Date.now()-started>=nextCheckpoint) {
          const checkpoint=await page.evaluate(async()=> {
            await flushPendingAutosave();
            if(JSON.stringify((await readAutosavePayload()).shapes)!==JSON.stringify(snapshotShapes()))throw Error('Endurance recovery differs');
            return {history:historyStorageEstimate(),historyEntries:editorHistory.entries.length,recovery:editorRecovery.status.state,
              nodes:document.getElementsByTagName('*').length,selectedHelpers:selectedShapeOutlineHelpers.size,masks:maskPreviewOutlines.size,
              cachePixels:vinylObjects().reduce((sum,o)=>sum+(o._cacheCanvas?.width||0)*(o._cacheCanvas?.height||0),0),
              cacheCount:vinylObjects().filter(o=>o._cacheCanvas).length,meshCount:editorRenderer.meshCount};
          });
          const cdp=await page.context().newCDPSession(page);
          try {checkpoint.heap=await cdp.send('Runtime.getHeapUsage');} finally {await cdp.detach();}
          checkpoints.push({seconds:(Date.now()-started)/1000,...checkpoint});
          if(options.primeHistory)check(checkpoint.historyEntries===80,'Endurance did not remain at the history retention boundary');
          fs.writeFileSync(path.join(output,'dense-endurance-checkpoints.json'),JSON.stringify(checkpoints,null,2));
          nextCheckpoint=Date.now()-started+60000;
        }
      }
      // Pan the viewport using each supported mouse button, without changing art.
      await trace.run(`${order}/${type}/pan-modes`,async()=> {
        const before=await h.snapshot(page),b=await page.locator('.upper-canvas').boundingBox();
        for(const button of ['right','middle']) {
          await page.mouse.move(b.x+b.width*.6,b.y+b.height*.4);await page.mouse.down({button});
          await page.mouse.move(b.x+b.width*.6+28,b.y+b.height*.4+16,{steps:12});await page.mouse.up({button});
          check(await page.evaluate(()=>!isPanning),'Pan remained captured after mouse-up');
        }
        check(await h.snapshot(page)===before,'Canvas panning changed dense artwork');
        await page.locator('#fitView').click();
      });
      await page.evaluate(async()=> {
        await flushPendingAutosave();
        if(JSON.stringify((await readAutosavePayload()).shapes)!==JSON.stringify(snapshotShapes()))throw Error('Rapid gesture recovery mismatch');
      });
      fs.writeFileSync(path.join(output,'dense-gesture-cases.json'),JSON.stringify(samples,null,2));
      await page.screenshot({path:path.join(output,`dense-gesture-${order}-${type}.png`)});
      // Restoring the replacement isolates shape-family comparisons.
      if(await h.snapshot(page)!==beforeReplace)await h.undo(page,beforeReplace);
      if(minimumSeconds) {
        // Keep real committed edits as well as undo probes so history reaches
        // its retention limit during endurance, instead of forever staying shallow.
        await h.select(page,'Human target');await page.locator('.upper-canvas').focus();
        await page.keyboard.press(round%2?'ArrowLeft':'ArrowRight');
        await page.waitForTimeout(350);
        if(await page.evaluate(()=>editorHistory.entries.length)>80)throw Error('Endurance history exceeded retention limit');
      }
      if(minimumSeconds&&Date.now()-started>=minimumSeconds*1000)break shapeCases;
    }
    round++;
    } while(Date.now()-started<minimumSeconds*1000);
    const expected=await h.snapshot(page);
    await trace.run('final/save-as',async()=> {
      await page.locator('#saveProjectAs').click();await h.type(page,'#textPromptInput','Dense gestures');
      await page.locator('#textPromptInput').press('Enter');await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
    });
    await trace.run('final/new-and-reopen',async()=> {
      await page.locator('#newCanvas').click();await page.waitForFunction(()=>!vinylObjects().length&&!recoveryRestoreDepth);
      await page.locator('#loadProject').click();
      await page.locator('.projectBrowserEntry').filter({has:page.getByText('Dense gestures',{exact:true})}).click();
      await page.locator('#selectProjectEntry').click();
      await page.waitForFunction(count=>vinylObjects().length===count&&!recoveryRestoreDepth,initial.layers);
      // Shape acceptance precedes asynchronous reference restoration. Wait for
      // the complete opened project, not only its already-installed layer list.
      if(initial.reference)await page.waitForFunction(({dimensions,opacity})=>!documentDirty
        &&editorReference.image?.width===dimensions[0]&&editorReference.image?.height===dimensions[1]
        &&Number(document.getElementById('overlayOpacity').value)===opacity,
      {dimensions:initial.reference,opacity:initial.referenceOpacity});
      check(await h.snapshot(page)===expected,'Final saved project did not reopen exactly');
      if(initial.reference)check(await page.evaluate(()=>!!editorReference.image),'Final reopen lost reference');
    });
    return {initial,samples,cycles,rounds:round,seconds:(Date.now()-started)/1000,checkpoints,rows:trace.rows,exactUndoAndRecovery:true,exactReopen:true};
  } finally {await trace.close();}
}
