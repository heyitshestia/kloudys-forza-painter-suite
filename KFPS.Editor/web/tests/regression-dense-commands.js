async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  page.setDefaultTimeout(30000);
  const initial = await h.setup(page, output, options);
  const trace = await h.monitor(page, output);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const prompt = async (button, value) => {
    await page.locator(button).click();
    await h.type(page, '#textPromptInput', value);
    await page.locator('#textPromptInput').press('Enter');
    await page.locator('#textPromptDialog').waitFor({state:'hidden'});
  };
  const batch = () => h.select(page, 'Dense batch', true);
  try {
    for (const order of ['below','above']) {
      if (initial.reference) {
        await page.locator('[data-tool-mode="overlay"]').click();
        await page.locator('#overlayLayerMode').selectOption(order);
      }
      await page.locator('[data-tool-mode="select"]').click();
      for (let round = 0; round < Number(options.rounds || 2); round++) {
        const tag = `${order}/${round+1}`;
        await trace.run(`${tag}/selection`, async () => {
          await h.select(page, 'Human target');
          const matchingShapeCount = await page.evaluate(() => {
            const type = selectedVinylObjects()[0].kloudy.type;
            return vinylObjects().filter(object => object.kloudy.type === type).length;
          });
          await page.locator('#selectSameShape').click();
          check(await page.evaluate(count => selectedVinylObjects().length===count && selectedVinylObjects().every(o=>objectToShape(o).type===1048706),matchingShapeCount), 'Same Shape returned different types or omitted matches');
          const selected = await page.evaluate(() => selectedVinylObjects().length);
          await page.locator('#selectInverseLayers').click();
          check(await page.evaluate(() => selectedVinylObjects().length) === initial.layers-selected, 'Invert lost a dense selection');
          await page.locator('#clearLayerSelection').click();
          await h.select(page,'Human target');
          await page.locator('#selectSameColor').click();
          check(await page.evaluate(() => selectedVinylObjects().length) === 1,'Same Color selected unrelated colors');
          await page.locator('#selectAllLayers').click();
          check(await page.evaluate(() => selectedVinylObjects().length) === initial.layers,'Select All omitted layers');
          await page.locator('#clearLayerSelection').click();
          check(await page.evaluate(() => selectedVinylObjects().length) === 0,'Clear selection retained layers');
        });
        for (const target of ['selection','canvas']) for (const direction of ['left','centerX','right','top','centerY','bottom']) {
          await batch();
          await page.locator('#alignTarget').selectOption(target);
          const before = await h.snapshot(page);
          await trace.run(`${tag}/align-${target}-${direction}`, async () => {
            await page.locator(`[data-align="${direction}"]`).click();
            check(await page.evaluate(direction => {
              const values = selectedVinylObjects().map(object=> {
                const r=object.getBoundingRect(true,true);
                return ({left:r.left,centerX:r.left+r.width/2,right:r.left+r.width,top:r.top,centerY:r.top+r.height/2,bottom:r.top+r.height})[direction];
              });
              return values.length===48 && Math.max(...values)-Math.min(...values)<.01;
            },direction),'Dense alignment failed');
            await h.undo(page,before);
          });
        }
        for (const axis of ['Horizontal','Vertical']) {
          await batch(); const before=await h.snapshot(page);
          await trace.run(`${tag}/distribute-${axis}`, async()=> {
            await page.locator(`#distribute${axis}`).click();
            check(await page.evaluate(axis=> {
              const values=selectedVinylObjects().map(o=>o.getCenterPoint()[axis==='Horizontal'?'x':'y']).sort((a,b)=>a-b);
              const step=(values.at(-1)-values[0])/(values.length-1);
              return values.every((v,i)=>Math.abs(v-values[0]-i*step)<.01);
            },axis),'Dense distribution failed');
            await h.undo(page,before);
          });
        }
        for (const [name,buttons] of [
          ['flips',['flipHorizontal','flipHorizontal','flipVertical','flipVertical']],
          ['rotation-buttons',['rotateRight','rotateLeft']],
          ['mask',['maskSelectedTool','maskSelectedTool']],
        ]) {
          await h.select(page,'Human target'); const before=await h.snapshot(page);
          await trace.run(`${tag}/${name}`,async()=> {
            for(const button of buttons) await page.locator(`#${button}`).click();
            check(await h.snapshot(page)===before,`${name} did not restore exact artwork`);
          });
        }
        await batch();
        await trace.run(`${tag}/group-visibility-lock`,async()=> {
          const before=await h.snapshot(page);
          for(const button of ['hideSelectedGroup','lockSelectedGroup']) {
            await page.locator(`#${button}`).click();
            check(await page.evaluate(button=>selectedGroupMembers().length===48 && selectedGroupMembers().every(o=>button==='hideSelectedGroup'?!o.visible:o.kloudy.locked),button),`${button} missed group members`);
            await page.locator(`#${button}`).click();
          }
          check(await h.snapshot(page)===before,'Group visibility/lock changed geometry or metadata');
        });
        await batch();
        await trace.run(`${tag}/group-pointer-transforms`,async()=> {
          for(const mode of ['move','rotate','scale']) {
            await batch();
            const before=await h.snapshot(page),g=await h.geometry(page);
            check(g.members===48,'Group pointer target did not contain48 shapes');
            if(mode==='move')await h.drag(page,g.grab,{x:g.grab.x+22,y:g.grab.y+13});
            if(mode==='scale')await h.drag(page,g.handles.br,{x:g.handles.br.x+17,y:g.handles.br.y+11});
            if(mode==='rotate') {
              const r=g.handles.mtr,c=g.center,dx=r.x-c.x,dy=r.y-c.y;
              await h.drag(page,r,{x:c.x+dx*Math.cos(.25)-dy*Math.sin(.25),y:c.y+dx*Math.sin(.25)+dy*Math.cos(.25)});
            }
            check(await h.snapshot(page)!==before,`Group ${mode} did nothing`);
            const after=JSON.parse(await h.snapshot(page)),previous=JSON.parse(before);
            check(after.every((shape,i)=>shape.editor_group_id==='dense-batch'||JSON.stringify(shape)===JSON.stringify(previous[i])),`Group ${mode} affected unrelated shapes`);
            await h.undo(page,before);
          }
        });
        await batch();
        await trace.run(`${tag}/duplicate-delete-undo-redo`,async()=> {
          const before=await h.snapshot(page);
          await page.locator('#duplicateLayer').click();
          await page.waitForFunction(count=>vinylObjects().length===count+48,initial.layers);
          const duplicated=await h.snapshot(page);
          check(await page.evaluate(()=>new Set(vinylObjects().map(o=>o.kloudy.editor_id)).size===vinylObjects().length),'Duplicate reused layer IDs');
          await h.undo(page,before);
          await page.locator('#redoBtn').click(); await page.waitForFunction(()=>!editorCommands.busy);
          check(await h.snapshot(page)===duplicated,'Dense duplicate redo differed');
          await h.undo(page,before);
          await batch();
          await page.locator('#copyLayer').click();await page.locator('#pasteLayer').click();
          await page.waitForFunction(count=>vinylObjects().length===count+48&&!editorCommands.busy,initial.layers);
          check(await page.evaluate(()=>new Set(vinylObjects().map(o=>o.kloudy.editor_id)).size===vinylObjects().length),'Paste reused layer IDs');
          await h.undo(page,before);
          await batch();
          await page.locator('#deleteLayer').click();
          await page.waitForFunction(count=>vinylObjects().length===count-48,initial.layers);
          await h.undo(page,before);
        });
        await trace.run(`${tag}/rename-save-reopen`,async()=> {
          await h.select(page,'Human target');
          await prompt('#renameSelectedLayer',`Human renamed ${order} ${round}`);
          check(await page.evaluate(()=>selectedVinylObjects()[0].kloudy.name.startsWith('Human renamed')),'Layer rename failed');
          await prompt('#renameSelectedLayer','Human target');
          await batch();
          await prompt('#renameSelectedGroup','Dense renamed group');
          check(await page.evaluate(()=>selectedGroupMembers().every(o=>o.kloudy.group_name==='Dense renamed group')),'Group rename missed members');
          await prompt('#renameSelectedGroup','Dense batch');
          const before=await h.snapshot(page);
          const name=`Dense commands ${order} ${round}`;
          await prompt('#saveProjectAs',name);
          await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
          await page.locator('#newCanvas').click();
          await page.waitForFunction(()=>vinylObjects().length===0);
          await page.locator('#loadProject').click();
          await page.locator('.projectBrowserEntry').filter({has:page.getByText(name,{exact:true})}).click();
          await page.locator('#selectProjectEntry').click();
          await page.waitForFunction(({count,reference,order,opacity})=>vinylObjects().length===count
            &&!recoveryRestoreDepth&&!documentDirty&&!editorRenderer.warmingDocument
            &&(!reference||editorReference.image?.width===reference[0]&&editorReference.image?.height===reference[1]
              &&overlayLayerMode===order&&Number(document.getElementById('overlayOpacity').value)===opacity),
            {count:initial.layers,reference:initial.reference,order,opacity:initial.referenceOpacity});
          check(await h.snapshot(page)===before,'Dense project reopen changed shapes/groups');
          if(initial.reference)check(await page.evaluate(()=>!!editorReference.image),'Reopen lost reference');
          await page.locator('#fitView').click();
        });
        await page.screenshot({path:path.join(output,`dense-commands-${order}-${round}.png`)});
      }
    }
    const recovery=await page.evaluate(async()=> {
      await flushPendingAutosave();
      return JSON.stringify((await readAutosavePayload()).shapes)===JSON.stringify(snapshotShapes());
    });
    check(recovery,'Final dense recovery did not match');
    return {initial,realInput:true,rows:trace.rows,exactRecovery:true};
  } finally {await trace.close();}
}
