async (page, options = {}) => {
  const h = require(path.join(__dirname,'dense-human-fixture.cjs'));
  const initial = await h.setup(page,output,{...options,layers:2900});
  const trace = await h.monitor(page,output);
  const check = (ok,message)=>{if(!ok)throw Error(message);};
  await h.select(page,'Human target');
  await page.locator('[data-panel="propertiesPane"]').click();
  try {
    for(const order of ['below','above']) {
      if(initial.reference) {
        await page.locator('[data-tool-mode="overlay"]').click();
        await page.locator('#overlayLayerMode').selectOption(order);
        await page.locator('[data-tool-mode="select"]').click();
      }
      await trace.run(`${order}/typed-numeric-preview-and-settle`,async()=> {
        for(let cycle=0;cycle<3;cycle++) {
          for(const [id,value] of [['xInput',`-180 + ${cycle}`],['yInput',`-190 + ${cycle}`],['sxInput',`1.5 + ${cycle}/10`],['syInput',`1.5 - ${cycle}/10`],['rotInput',`${cycle+1}*17`],['skewInput',`${cycle+1}*3`]]) {
            await h.type(page,`#${id}`,value); await page.locator(`#${id}`).press('Enter');
            check(await page.evaluate(()=>editorRenderer.active),'Valid numeric edit did not enter preview');
          }
        }
        await page.waitForFunction(()=>!editorRenderer.active);
        check(await page.evaluate(()=>canvas.lowerCanvasEl.style.visibility!=='hidden' && editorRenderer.renderer.element.hidden),'Final numeric scene did not return to Fabric');
      });
      await trace.run(`${order}/invalid-input-and-label-cancel`,async()=> {
        const before=await h.snapshot(page);
        await h.type(page,'#sxInput','0'); await page.locator('#sxInput').press('Enter');
        check(await page.locator('#sxInput').getAttribute('aria-invalid')==='true','Zero scale accepted');
        check(await h.snapshot(page)===before,'Rejected scale changed geometry');
        await page.locator('#sxInput').press('Escape');
        const label=await page.locator('[data-numeric-for="rotInput"]').boundingBox();
        const x=label.x+label.width/2,y=label.y+label.height/2;
        await page.mouse.move(x,y); await page.mouse.down();
        await page.mouse.move(x+40,y,{steps:20});
        check(await h.snapshot(page)!==before,'Numeric label pointer did not preview a change');
        await page.keyboard.press('Escape'); await page.mouse.up();
        check(await h.snapshot(page)===before,'Cancelled numeric preview changed data');
        await page.waitForFunction(()=>!editorRenderer.active);
      });
      const pixels=await page.evaluate(()=> {
        const selected=canvas.getActiveObject();
        canvas.discardActiveObject();
        editorRenderer.endHybridRenderNow(); canvas.renderAll();
        if(!editorRenderer.hybridRenderNow()) throw Error('Dense GPU scene could not render for comparison');
        const {gl,element}=editorRenderer.renderer;
        const ratio=canvas.getRetinaScaling();
        let samples=0,maxDifference=0;
        const mismatches=[];
        for(let y=30;y<canvas.height-30;y+=29)for(let x=30;x<canvas.width-30;x+=31) {
          const px=Math.round(x*ratio),py=Math.round(y*ratio);
          const neighbors=canvas.contextContainer.getImageData(px-1,py-1,3,3).data;
          const expected=Array.from(neighbors.slice(16,20));
          if(Array.from({length:9},(_,i)=>i).some(i=>expected.some((v,c)=>Math.abs(v-neighbors[i*4+c])>2)))continue;
          const actual=new Uint8Array(4);
          gl.readPixels(px,element.height-1-py,1,1,gl.RGBA,gl.UNSIGNED_BYTE,actual);
          const difference=Math.max(...expected.map((v,i)=>Math.abs(v-actual[i])));
          maxDifference=Math.max(maxDifference,difference);samples++;
          if(difference>4 && mismatches.length<20)mismatches.push({px,py,expected,actual:[...actual],difference});
        }
        if(selected)canvas.setActiveObject(selected);
        return {samples,maxDifference,mismatches,ratio,fabric:[canvas.contextContainer.canvas.width,canvas.contextContainer.canvas.height],gpu:[element.width,element.height]};
      });
      fs.writeFileSync(path.join(output,`numeric-preview-${order}-pixels.json`),JSON.stringify(pixels));
      check(pixels.samples>=80&&pixels.maxDifference<=4,'Dense numeric preview pixels differ: '+JSON.stringify(pixels));
    }
    await trace.run('numeric-preview-render-failure',async()=> {
      await page.evaluate(()=> {
        window.numericFailureGl=editorRenderer.renderer.gl;
        window.numericOriginalClear=numericFailureGl.clear;
        numericFailureGl.clear=()=>{throw Error('Injected numeric preview draw failure');};
      });
      try {
        await h.type(page,'#xInput','-150'); await page.locator('#xInput').press('Enter');
        await page.waitForFunction(()=>!editorRenderer.active&&!!editorRenderer.disabledReason);
        check(await page.evaluate(()=>objectToShape(selectedVinylObjects()[0]).data[0]===-150),'Rendering failure dropped committed numeric edit');
        check(await page.evaluate(()=>canvas.lowerCanvasEl.style.visibility!=='hidden'),'Rendering failure left a hidden canvas');
      } finally {await page.evaluate(()=>{numericFailureGl.clear=numericOriginalClear;});}
    });
    await page.evaluate(async()=> {
      await flushPendingAutosave();
      if(JSON.stringify((await readAutosavePayload()).shapes)!==JSON.stringify(snapshotShapes()))throw Error('Numeric fallback recovery changed shapes');
    });
    await page.locator('#saveProjectAs').click();
    await h.type(page,'#textPromptInput','Numeric fallback checkpoint');
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(()=>!projectSaveInProgress&&!documentDirty);
    await page.screenshot({path:path.join(output,'numeric-preview-final.png')});
    return {initial,typedCommits:36,invalidEdits:2,cancelledPointerDrags:2,pixelComparisons:2,exactRecovery:true,rows:trace.rows};
  } finally {await trace.close();}
}
