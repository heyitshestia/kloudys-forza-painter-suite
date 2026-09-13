async (page,options={}) => {
  page.setDefaultTimeout(15000);
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  const check=(ok,message)=>{if(!ok)throw Error(message);};
  await h.setup(page,output,{layers:2450});
  const fixture=JSON.parse(fs.readFileSync(path.join(output,'dense-input.json')));
  fixture.shapes.forEach(shape=>shape.color=[50,90,150,255]);
  const target=fixture.shapes.find(shape=>shape.editor_id==='dense-target');
  target.color=[220,30,80,160];
  target.data[1]=-650;
  const input=path.join(output,'translucent-dense-input.json');
  fs.writeFileSync(input,JSON.stringify(fixture));
  await h.fileInput(page,'#jsonInput',input);
  await page.locator('#confirmationDialogConfirm').click();
  await page.waitForFunction(()=>vinylObjects().length===2450&&!recoveryRestoreDepth
    &&vinylObjects().find(o=>o.kloudy.editor_id==='dense-target')?.opacity===160/255);
  const reference=path.join(output,'neutral-reference.png');
  const encoded=await page.evaluate(()=>{
    const c=document.createElement('canvas');c.width=5888;c.height=2816;
    const ctx=c.getContext('2d');ctx.fillStyle='#b0b0b0';ctx.fillRect(0,0,c.width,c.height);
    return c.toDataURL().split(',')[1];
  });
  fs.writeFileSync(reference,Buffer.from(encoded,'base64'));
  const resources=await page.evaluate(()=>[
    ['Community_Vinyls_1',11],['Community_Vinyls_2',18],['Community_Vinyls_2',13],
    ['Gradient_Shapes',1],['Primitives',30],
  ].map(([family,slot])=>({family,slot,type:editorCatalog.resourceToTypeCode(family,slot)})));
  const cases=options.family?resources.filter(resource=>resource.family===options.family):resources;
  check(cases.length>0,'No matching translucency cases');
  const samples=[], rows=[];
  async function geometry() {
    check(await page.evaluate(()=>selectedVinylObjects().length===1
      &&selectedVinylObjects()[0].kloudy.editor_id==='dense-target'),'Gesture selected a different layer');
    for(let attempt=0;attempt<4;attempt++) {
      const g=await h.geometry(page),b=await page.locator('.upper-canvas').boundingBox();
      if(Object.values(g.handles).every(p=>p.x>b.x+30&&p.x<b.x+b.width-30&&p.y>b.y+30&&p.y<b.y+b.height-30))return g;
      await page.mouse.move(b.x+b.width/2,b.y+b.height/2);
      await page.mouse.wheel(0,250);await page.waitForTimeout(250);
    }
    throw Error('Could not frame target handles inside the canvas');
  }
  async function pixels(label) {
    fs.writeFileSync(path.join(output,'motion-phase.json'),JSON.stringify({label}));
    const value=await page.evaluate(async()=>{
      await new Promise(resolve=>requestAnimationFrame(resolve));
      const r=editorRenderer.renderer;
      if(!editorRenderer.active||r.element.hidden||canvas.lowerCanvasEl.style.visibility!=='hidden')throw Error('Motion preview was not displayed');
      const o=selectedVinylObjects()[0], w=canvas.width, height=canvas.height;
      if(selectedVinylObjects().length!==1||o.kloudy.editor_id!=='dense-target')throw Error('Pixel oracle requires the intended target');
      const c=document.createElement('canvas');c.width=w;c.height=height;
      const ctx=c.getContext('2d',{willReadFrequently:true});
      ctx.setTransform(...canvas.viewportTransform);o.render(ctx);
      const expected=ctx.getImageData(0,0,w,height).data;
      const actual=new Uint8Array(w*height*4);
      r.gl.readPixels(0,0,w,height,r.gl.RGBA,r.gl.UNSIGNED_BYTE,actual);
      const coverage=buffer=>{
        let tested=0,visible=0;
        for(let y=0;y<height;y++)for(let x=0;x<w;x++) {
          const i=(y*w+x)*4,j=((height-1-y)*w+x)*4;
          if(expected[i+3]<75)continue;
          tested++;
          // Signature Pink's background has ~30 red-green contrast. It must
          // never count as a visible red shape when that shape disappears.
          if(buffer[j]-buffer[j+1]>45)visible++;
        }
        return {tested,visible,coverage:visible/Math.max(1,tested)};
      };
      const measured=coverage(actual);
      let negativeControl=null;
      if(o.kloudy.alpha_mesh_image&&!window.alphaNegativeControlChecked) {
        const oldFlag=o.kloudy.alpha_mesh_image;
        try {
          // The mesh is already cached. Disable only raster compensation to
          // reproduce the old GPU transform, without changing the Fabric image.
          o.kloudy.alpha_mesh_image=false;
          if(!editorRenderer.hybridRenderNow())throw Error('Negative-control render failed');
          r.gl.readPixels(0,0,w,height,r.gl.RGBA,r.gl.UNSIGNED_BYTE,actual);
          negativeControl=coverage(actual);
        } finally {
          o.kloudy.alpha_mesh_image=oldFlag;
          editorRenderer.hybridRenderNow();
        }
        if(negativeControl.coverage>.25)throw Error('Pixel oracle accepted the old disappearing-shape bug: '+JSON.stringify(negativeControl));
        window.alphaNegativeControlChecked=true;
      }
      c.width=c.height=1;
      return {...measured,negativeControl,active:true,opacity:o.opacity,fill:o.fill,zoom:canvas.getZoom()};
    });
    samples.push({label,...value});
    fs.writeFileSync(path.join(output,'motion-pixel-samples.json'),JSON.stringify(samples,null,2));
    check(value.tested>=8&&value.coverage>=.7,'In-motion shape pixels missing: '+JSON.stringify(samples.at(-1)));
  }
  for(const order of ['none','below','above']) {
    if(order==='below') {
      await page.locator('[data-tool-mode="overlay"]').click();
      await h.fileInput(page,'#overlayInput',reference);
      await page.waitForFunction(()=>editorReference.image&&!recoveryRestoreDepth);
      await page.locator('#overlayOpacity').focus();await page.keyboard.press('Home');
      for(let i=0;i<25;i++)await page.keyboard.press('ArrowRight');
    }
    if(order!=='none') {
      await page.locator('[data-tool-mode="overlay"]').click();
      await page.locator('#overlayLayerMode').selectOption(order);
    }
    for(const resource of cases) {
      await h.select(page,'Human target');
      const original=await h.snapshot(page);
      await page.locator('#shapePlacementMode').selectOption('replace');
      await page.locator('[data-tool-mode="shapeLibrary"]').click();
      await page.locator('#shapeFamily').selectOption(resource.family);
      await h.type(page,'#shapeSearch',String(resource.type));
      await page.locator('#shapeGrid .shapeTile img').first().click();
      await page.waitForFunction(type=>selectedVinylObjects()[0]?.kloudy.type===type,resource.type);
      await page.locator('[data-tool-mode="select"]').click();
      await page.locator('#fitView').click();
      const before=await h.snapshot(page), prefix=`${order}/${resource.family}/${resource.slot}`;
      const monitor=await h.monitor(page,output);
      // Timing is measured on an uninterrupted pointer chain, not on pixel readback.
      await monitor.run(prefix+'/continuous',async()=>{
        for(let cycle=0;cycle<3;cycle++) {
          const g=await geometry(),p=g.handles.mtr,c=g.center,dx=p.x-c.x,dy=p.y-c.y;
          await h.drag(page,p,{x:c.x+dx*.94-dy*.34,y:c.y+dx*.34+dy*.94});
          const rotated=await geometry();
          check(Math.abs(rotated.angle-g.angle)>5,'Rotation did not happen');
          await h.drag(page,rotated.grab,{x:rotated.grab.x+12,y:rotated.grab.y+6});
          const moved=await geometry();
          check(Math.hypot(moved.left-rotated.left,moved.top-rotated.top)>.1,'Immediate move failed');
          await page.mouse.move(moved.center.x,moved.center.y);
          for(const delta of [-120,120,-120,120])await page.mouse.wheel(0,delta);
          const z=await geometry();
          await h.drag(page,z.grab,{x:z.grab.x-12,y:z.grab.y-6});
        }
      });
      await monitor.close();rows.push(...monitor.rows);
      for(const kind of ['move','rotate','resize','skew','pan-right','pan-middle','zoom']) {
        const g=await geometry();
        if(kind==='zoom') {
          await page.mouse.move(g.center.x,g.center.y);
          await page.mouse.wheel(0,-120);await pixels(prefix+'/'+kind);await page.mouse.wheel(0,120);
        } else {
          const button=kind==='pan-right'?'right':kind==='pan-middle'?'middle':'left';
          const start=kind==='rotate'?g.handles.mtr:kind==='resize'||kind==='skew'?g.handles.br:g.grab;
          if(kind==='skew')await page.keyboard.down('Shift');
          try {
            await page.mouse.move(start.x,start.y);await page.mouse.down({button});
            await page.mouse.move(start.x+15,start.y+9,{steps:6});
            await pixels(prefix+'/'+kind);
          } finally {await page.mouse.up({button});if(kind==='skew')await page.keyboard.up('Shift');}
        }
      }
      await page.waitForFunction(()=>!editorRenderer.active);
      check(await page.evaluate(()=>canvas.lowerCanvasEl.style.visibility!=='hidden'),'Still renderer remained hidden');
      for(let i=0;i<35&&await h.snapshot(page)!==original;i++) {
        await page.locator('#undoBtn').click();await page.waitForFunction(()=>!editorCommands.busy);
      }
      check(await h.snapshot(page)===original,'Motion and replacement failed exact undo');
      check(before!==original,'Replacement did not change resource');
      await page.locator('#fitView').click();
    }
  }
  await page.evaluate(async()=>{
    await flushPendingAutosave();
    if(JSON.stringify((await readAutosavePayload()).shapes)!==JSON.stringify(snapshotShapes()))throw Error('Recovery differs from artwork');
  });
  fs.writeFileSync(path.join(output,'translucent-timing.json'),JSON.stringify(rows,null,2));
  await page.screenshot({path:path.join(output,'translucent-dense-final.png')});
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Translucency checkpoint');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
  return {scene:await h.scene(page),cases:cases.length*3,samples,rows,exactUndo:true,exactRecovery:true};
}
