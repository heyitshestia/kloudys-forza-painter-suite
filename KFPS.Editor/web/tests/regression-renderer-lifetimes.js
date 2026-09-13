async page => {
  await page.evaluate(async () => {
    await loadPayload({shapes:Array.from({length:300},(_,i)=>({type:1048677,
      color:[160,95,200,255],data:[i%30*25-375,Math.floor(i/30)*25-125,.2,.2,0,0,0]}))});
  });
  const allocations=await page.evaluate(()=>{
    const renderer=editorRenderer.initHybridRenderer(), gl=renderer.gl, results=[];
    const track=()=>{
      const originals={},live={Shader:new Set(),Program:new Set(),Buffer:new Set(),Texture:new Set()};
      for(const kind of Object.keys(live)){
        const make=`create${kind}`,drop=`delete${kind}`;
        originals[make]=gl[make];originals[drop]=gl[drop];
        gl[make]=function(...args){const value=originals[make].apply(this,args);if(value)live[kind].add(value);return value;};
        gl[drop]=function(value){live[kind].delete(value);return originals[drop].call(this,value);};
      }
      return {live,restore(){
        for(const [kind,values] of Object.entries(live))for(const value of values)originals[`delete${kind}`].call(gl,value);
        Object.assign(gl,originals);
      }};
    };
    for(const failure of ['fragment-compile','late-initialization']){
      editorRenderer.reset();
      const t=track();
      const shaderParameter=gl.getShaderParameter, bufferData=gl.bufferData;
      let checks=0;
      try{
        if(failure==='fragment-compile'){
          gl.getShaderParameter=function(...args){if(++checks===2)return false;return shaderParameter.apply(this,args);};
        }else{
          gl.bufferData=()=>{throw Error('Injected late initialization failure');};
        }
        if(editorRenderer.initHybridRenderer())throw Error('Injected graphics failure was not exercised');
        results.push({failure,live:Object.fromEntries(Object.entries(t.live).map(([key,value])=>[key,value.size]))});
      }finally{
        gl.getShaderParameter=shaderParameter;gl.bufferData=bufferData;
        editorRenderer.reset();t.restore();
        editorRenderer.initHybridRenderer();
      }
    }
    return results;
  });
  await page.evaluate(async()=>{
    const gl=editorRenderer.renderer.gl, loss=gl.getExtension('WEBGL_lose_context');
    if(!loss)throw Error('Context-loss extension unavailable');
    editorRenderer.beginHybridRender('lifetime regression');
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    window.lifetimeHud=updateHud;window.lifetimeContext=loss;
    updateHud=()=>{throw Error('Injected HUD failure during GPU cleanup');};
    loss.loseContext();
  });
  let lost;
  try {
    await page.waitForTimeout(350);
    lost=await page.evaluate(()=>({released:editorRenderer.renderer===null,reason:editorRenderer.disabledReason,
      visible:canvas.lowerCanvasEl.style.visibility!=='hidden',active:editorRenderer.active}));
  } finally {
    await page.evaluate(()=>{updateHud=lifetimeHud;lifetimeContext.restoreContext();});
  }
  await page.waitForTimeout(350);
  fs.writeFileSync(path.join(output,'renderer-lifetimes.json'),JSON.stringify({allocations,lost},null,2));
  for(const row of allocations)if(Object.values(row.live).some(Boolean))throw Error(`Unreleased partial GPU resources: ${JSON.stringify(allocations)}`);
  if(!lost.released||lost.reason!=='WebGL context lost'||!lost.visible||lost.active)throw Error(`HUD failure interrupted context cleanup: ${JSON.stringify(lost)}`);
  const restored=await page.evaluate(()=>{
    if(!editorRenderer.renderer||editorRenderer.renderer.gl.isContextLost()||!editorRenderer.hybridRenderNow())throw Error('Renderer failed to recover');
    const pixel=new Uint8Array(4),gl=editorRenderer.renderer.gl;
    gl.readPixels(100,100,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);
    if(pixel[3]!==255)throw Error('Restored renderer is blank');
    return true;
  });
  return {allocations,lost,restored};
}
