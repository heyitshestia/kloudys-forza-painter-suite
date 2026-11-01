const test=require('node:test'), assert=require('node:assert/strict');
const {create}=require('../editor-renderer.js');

function fixture(t, fault={}) {
  const live={Shader:new Set(),Program:new Set(),Buffer:new Set(),Texture:new Set()}, events=new Map(), frames=new Map();
  let serial=0, shaderChecks=0, program=null, generation=0, draws=0;
  const enabled=new Set(), counters={}, records=[];
  const gl=new Proxy({
    getShaderParameter(){return ++shaderChecks!==fault.shaderCheck;},getShaderInfoLog:()=>'',
    getProgramParameter:()=>!fault.link,getProgramInfoLog:()=>'',
    getAttribLocation(p,name){const value={a_position:0,a_alpha:1,a_texcoord:1,a_world0:2,a_world1:3,a_world2:4,a_color:5}[name];p.locations.add(value);return value;},
    getUniformLocation:()=>({}), getError:()=>0,isContextLost:()=>false,
    getParameter:key=>key==='MAX_TEXTURE_SIZE'?4096:16, getExtension:()=>({vertexAttribDivisorANGLE(){},drawArraysInstancedANGLE(){draw();}}),
    useProgram(value){program=value;}, enableVertexAttribArray(value){enabled.add(value);},disableVertexAttribArray(value){enabled.delete(value);},
    drawArrays:()=>draw(),bufferData(){if(fault.bufferData)throw Error('allocation failure');},
  },{get(object,key){if(key in object)return object[key];if(key==='NO_ERROR')return 0;return /^[A-Z_]+$/.test(key)?key:()=>{};}});
  function draw(){assert.deepEqual([...enabled].sort(),[...program.locations].sort(),'draw inherited attributes from another program');draws++;}
  for(const kind of Object.keys(live)){
    gl[`create${kind}`]=()=>{
      counters[kind]=(counters[kind]||0)+1;
      if(fault.nullKind===kind&&counters[kind]===fault.nullAt)return null;
      const value={id:++serial,locations:new Set()};live[kind].add(value);return value;
    };
    gl[`delete${kind}`]=value=>live[kind].delete(value);
  }
  const element={width:600,height:400,hidden:true,getContext:()=>gl,
    addEventListener(name,fn){events.set(name,fn);},removeEventListener(name,fn){if(events.get(name)===fn)events.delete(name);}};
  const canvas={width:600,height:400,viewportTransform:[1,0,0,1,0,0],backgroundColor:'#123456',
    lowerCanvasEl:{style:{visibility:''}},cancelRequestedRender(){},requestRenderAll(){},renderTop(){}};
  const objects=Array.from({length:300},()=>({kloudy:{resource_family:'Primitives',resource_index:1,type:1048677},
    fill:'#ffffff',opacity:1,calcTransformMatrix:()=>[1,0,0,1,0,0]}));
  const reference={image:null,layerMode:()=> 'below'};
  const view={element:()=>element,cssColor:()=> '#ffffff',text(){},mode:()=> 'select',hud(){if(fault.hud)throw Error('HUD failure');}};
  const oldFrame=globalThis.requestAnimationFrame, oldCancel=globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame=fn=>{frames.set(++serial,fn);return serial;};
  globalThis.cancelAnimationFrame=id=>frames.delete(id);
  const owner=create({scene:{canvas:()=>canvas,objects:()=>objects,selected:()=>[],visible:()=>true,toolMode:()=> 'select',generation:()=>generation,documentIdentity:()=>generation},
    reference,view,catalog:{payloads:new Map([['shape',{Vertices:[[0,0],[1,0],[0,1]],Indices:[0,1,2]}]]),key:()=> 'shape',isGradient:()=>false},
    geometry:{vertex:p=>({x:p[0],y:p[1],alpha:1}),indices:p=>p},colors:{normalize:p=>p,parse:()=>[10,20,30,255]},
    schedule:{nextFrame:async()=>{}},diagnostics:{record(...args){if(fault.observer)throw Error('observer failure');records.push(args);}},
    maxLayers:3000,KfpsI18n:{t:s=>s,error:s=>s}});
  t.mock.method(console,'warn',()=>{});t.mock.method(console,'error',()=>{});
  let cleaned=false;
  const cleanup=()=>{if(cleaned)return;cleaned=true;owner.dispose();globalThis.requestAnimationFrame=oldFrame;globalThis.cancelAnimationFrame=oldCancel;};
  t.after(cleanup);
  return {owner,live,events,frames,records,canvas,reference,gl,element,fault,cleanup,objects,
    replaceIdentity(){generation++;},
    nextFrame(){const batch=[...frames.values()];frames.clear();batch.forEach(fn=>fn());},
    get draws(){return draws;}};
}

test('inactive pages trim largest caches to a budget, then expire without changing objects',t=>{
  t.mock.timers.enable({apis:['setTimeout','Date']});
  const f=fixture(t), removed=[];
  f.objects.forEach((object,index)=>Object.assign(object,{_cacheCanvas:{width:256,height:256},
    _removeCacheCanvas(){removed.push(index);this._cacheCanvas=null;}}));
  f.objects[0]._cacheCanvas={width:4096,height:4096};
  const identity=f.objects.map(o=>o.kloudy);
  assert.ok(f.owner.hybridRenderNow());
  f.owner.setPageVisible(false);
  t.mock.timers.tick(4999);assert.equal(removed.length,0);
  t.mock.timers.tick(1);assert.deepEqual(removed,[0]);
  assert.ok(f.owner.inactiveRetainedBytes<=96*1024*1024);
  t.mock.timers.tick(25000);assert.equal(removed.length,300);
  assert.equal(f.owner.inactiveCacheReleased,true);
  assert.equal(f.owner.meshCount,0);
  assert.deepEqual(f.objects.map(o=>o.kloudy),identity);
  assert.equal(f.owner.beginHybridRender(),false);
  f.owner.setPageVisible(true);
  assert.equal(f.owner.inactiveCacheReleased,false);
  assert.ok(f.owner.active);
  assert.ok(f.owner.hybridRenderNow());
});

test('small documents stay warm and a recent return extends bounded retention',t=>{
  t.mock.timers.enable({apis:['setTimeout','Date'],now:100000});
  const f=fixture(t);let removed=0;
  f.objects[0]._cacheCanvas={width:256,height:256};
  f.objects[0]._removeCacheCanvas=function(){removed++;this._cacheCanvas=null;};
  f.owner.setPageVisible(false);t.mock.timers.tick(6000);
  assert.equal(removed,0);assert.equal(f.owner.inactiveCacheReleased,false);
  f.owner.setPageVisible(true);t.mock.timers.tick(1000);
  f.owner.setPageVisible(false);t.mock.timers.tick(30000);assert.equal(removed,0);
  t.mock.timers.tick(30000);assert.equal(removed,1);
});

test('low-memory devices use a smaller cap and nested cache ownership is visited once',t=>{
  t.mock.timers.enable({apis:['setTimeout','Date']});
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,'navigator');
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{deviceMemory:4}});
  t.after(()=>{if(descriptor)Object.defineProperty(globalThis,'navigator',descriptor);else delete globalThis.navigator;});
  const f=fixture(t);let removed=0;
  const nested={_cacheCanvas:{width:4096,height:4096},_removeCacheCanvas(){removed++;this._cacheCanvas=null;}};
  f.objects[0]._objects=[nested];f.objects[0].clipPath=nested;nested.clipPath=f.objects[0];
  f.objects[1]._cacheCanvas={width:2048,height:2048};
  f.objects[1]._removeCacheCanvas=function(){this._cacheCanvas=null;};
  f.owner.setPageVisible(false);t.mock.timers.tick(5000);
  assert.equal(removed,1);assert.equal(f.owner.inactiveRetainedBytes,16*1024*1024);
  t.mock.timers.tick(25000);assert.equal(f.owner.inactiveRetainedBytes,0);
});

test('a delayed background timer expires rather than starting another retention window',t=>{
  t.mock.timers.enable({apis:['setTimeout','Date'],now:100000});
  const f=fixture(t);let removed=0;
  f.objects[0]._cacheCanvas={width:256,height:256};
  f.objects[0]._removeCacheCanvas=function(){removed++;this._cacheCanvas=null;};
  f.owner.setPageVisible(false);t.mock.timers.tick(90000);
  assert.equal(removed,1);assert.equal(f.owner.inactiveRetainedBytes,0);
  assert.equal(f.owner.inactiveCacheReleased,true);
});

test('rapid switching and disposal cancel pending inactive cleanup',t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  const f=fixture(t);let removed=0;
  f.objects[0]._cacheCanvas={width:256,height:256};
  f.objects[0]._removeCacheCanvas=()=>removed++;
  for(let i=0;i<20;i++) {f.owner.setPageVisible(false);t.mock.timers.tick(100);f.owner.setPageVisible(true);}
  t.mock.timers.tick(6000);assert.equal(removed,0);
  f.owner.setPageVisible(false);f.owner.dispose();t.mock.timers.tick(6000);
  assert.equal(removed,0);assert.equal(f.frames.size,0);
});

test('inactive cache resume shows GPU preview before rebuilding Fabric in bounded batches',t=>{
  t.mock.timers.enable({apis:['setTimeout','Date']});
  const f=fixture(t), painted=[];let requests=0,clock=0;
  t.mock.method(performance,'now',()=>++clock);
  f.canvas.requestRenderAll=()=>requests++;
  f.objects.forEach((object,index)=>Object.assign(object,{canvas:f.canvas,visible:true,
    shouldCache:()=>true,renderCache:()=>painted.push(index)}));
  f.owner.setPageVisible(false);t.mock.timers.tick(5000);t.mock.timers.tick(25000);requests=0;
  f.owner.setPageVisible(true);
  assert.equal(requests,0,'Resume must not queue an unbounded cold Fabric repaint');
  f.nextFrame();assert.ok(painted.length>0&&painted.length<300);assert.equal(f.element.hidden,false);
  while(f.owner.warmingDocument)f.nextFrame();
  assert.equal(painted.length,300);assert.equal(requests,1);
});

test('quick return requeues interrupted paint and hidden late work cannot grow GPU caches',async t=>{
  t.mock.timers.enable({apis:['setTimeout']});
  const f=fixture(t);let paints=0;
  f.canvas.requestRenderAll=()=>paints++;
  assert.ok(f.owner.hybridRenderNow());
  f.owner.setPageVisible(false);paints=0;
  f.owner.setPageVisible(true);assert.equal(paints,1);
  f.owner.setPageVisible(false);t.mock.timers.tick(5000);
  assert.equal(f.owner.initHybridRenderer(),null);
  assert.equal(f.owner.resizeHybridRenderer(),false);
  await f.owner.prewarmHybridMeshesForObjects();
  assert.equal(f.owner.meshCount,0);assert.equal(f.element.width,1);
  f.owner.setPageVisible(true);assert.ok(f.owner.hybridRenderNow());
});

test('partial program, buffer and texture failures release all owned allocations',t=>{
  for(const fault of [{shaderCheck:1},{shaderCheck:2},{shaderCheck:4},{link:true},{bufferData:true},
    {nullKind:'Buffer',nullAt:1},{nullKind:'Buffer',nullAt:2},{nullKind:'Texture',nullAt:1}]){
    const f=fixture(t,fault);
    assert.equal(f.owner.initHybridRenderer(),null,JSON.stringify(fault));
    for(const [kind,values] of Object.entries(f.live))assert.equal(values.size,0,`${kind}: ${JSON.stringify(fault)}`);
    f.cleanup();
  }
});

test('context reset, display failure, observer failure and disposal keep ownership bounded',t=>{
  const f=fixture(t,{hud:true,observer:true});
  assert.ok(f.owner.hybridRenderNow());
  assert.ok(f.owner.beginHybridRender());f.nextFrame();
  assert.equal(f.canvas.lowerCanvasEl.style.visibility,'hidden');
  f.events.get('webglcontextlost')({preventDefault(){}});
  assert.equal(f.owner.active,false);assert.equal(f.owner.renderer,null);
  assert.equal(f.canvas.lowerCanvasEl.style.visibility,'');
  for(const values of Object.values(f.live))assert.equal(values.size,0);
  f.events.get('webglcontextrestored')();
  assert.ok(f.owner.hybridRenderNow());
  f.owner.beginHybridRender();assert.equal(f.frames.size,1);
  f.owner.dispose();f.nextFrame();
  assert.equal(f.frames.size,0);assert.equal(f.events.size,0);
  assert.equal(f.owner.initHybridRenderer(),null);assert.equal(f.owner.beginHybridRender(),false);
  for(const values of Object.values(f.live))assert.equal(values.size,0);
});

test('shape and reference passes switch only their own vertex attributes',t=>{
  const f=fixture(t);
  f.reference.image={visible:true,opacity:1,width:20,height:20,getElement:()=>({width:20,height:20}),calcTransformMatrix:()=>[1,0,0,1,0,0]};
  assert.ok(f.owner.hybridRenderNow(),f.owner.disabledReason);assert.ok(f.draws>=2);
  f.owner.reset();assert.ok(f.owner.hybridRenderNow());
  f.fault.bufferData=true;
  f.owner.reset();assert.equal(f.owner.hybridRenderNow(),false);
  assert.equal(f.canvas.lowerCanvasEl.style.visibility,'');
});

test('large visible reference uses preview below the layer threshold without changing the ordinary threshold',t=>{
  const f=fixture(t);
  assert.equal(f.owner.hybridShouldUse([]),false);
  assert.equal(f.owner.hybridShouldUse(Array(299)),false);
  assert.equal(f.owner.hybridShouldUse(Array(300)),true);
  f.reference.image={width:2048,height:2048,visible:true,opacity:.45};
  assert.equal(f.owner.hybridShouldUse([]),true);
  assert.equal(f.owner.hybridShouldUse([{}]),true);
  for(const change of [{visible:false},{opacity:0},{width:2047},{width:Infinity}]){
    Object.assign(f.reference.image,{width:2048,height:2048,visible:true,opacity:.45},change);
    assert.equal(f.owner.hybridShouldUse([{}]),false,JSON.stringify(change));
  }
  Object.assign(f.reference.image,{width:5888,height:2816,visible:true,opacity:1});
  f.owner.reset('device failure');
  assert.equal(f.owner.hybridShouldUse([]),false);
});

test('document cache preparation yields, skips detached layers and returns to ordinary drawing',t=>{
  const f=fixture(t), painted=[], order=[];
  let clock=0;
  t.mock.method(performance,'now',()=>++clock);
  f.canvas.cancelRequestedRender=()=>order.push('cancel-old');
  f.canvas.requestRenderAll=()=>order.push('request-fabric');
  f.canvas.skipOffscreen=true;
  f.objects.forEach((object,index)=>Object.assign(object,{canvas:f.canvas,visible:true,
    shouldCache:()=>true,isOnScreen:()=>index!==3,renderCache:()=>painted.push(index)}));
  f.objects[0].canvas=null;f.objects[1].visible=false;f.objects[2].opacity=0;
  assert.equal(f.owner.warmDocumentCaches(),true);
  assert.deepEqual(order,['cancel-old','request-fabric']);
  f.nextFrame();assert.equal(f.owner.warmingDocument,true);
  assert.equal(f.canvas.lowerCanvasEl.style.visibility,'hidden');
  for(let i=0;i<200&&f.owner.warmingDocument;i++)f.nextFrame();
  assert.equal(f.owner.warmingDocument,false);assert.equal(f.owner.active,false);
  assert.equal(f.canvas.lowerCanvasEl.style.visibility,'');
  assert.deepEqual(painted,Array.from({length:296},(_,i)=>i+4));
  assert.ok(f.records.some(([kind,r])=>kind==='phase'&&r.phase==='document-cache'&&r.state==='finished'));
});

test('warmup cancellation cannot end a newer gesture or retain a retired document',t=>{
  for(const action of ['gesture','identity','reset','dispose']){
    const f=fixture(t);
    assert.ok(f.owner.warmDocumentCaches());
    if(action==='gesture')f.owner.beginHybridRender('move');
    if(action==='identity')f.replaceIdentity();
    if(action==='reset')f.owner.reset();
    if(action==='dispose')f.owner.dispose();
    f.nextFrame();
    assert.equal(f.owner.warmingDocument,false,action);
    assert.equal(f.owner.active,action==='gesture',action);
    if(action!=='gesture')assert.equal(f.canvas.lowerCanvasEl.style.visibility,'',action);
    f.cleanup();
  }
});

test('warmup failure and unavailable preview leave ordinary drawing usable',t=>{
  const f=fixture(t);
  Object.assign(f.objects[0],{canvas:f.canvas,visible:true,shouldCache:()=>true,
    renderCache(){throw TypeError('injected cache failure');}});
  assert.ok(f.owner.warmDocumentCaches());f.nextFrame();
  assert.equal(f.owner.warmingDocument,false);assert.equal(f.owner.active,false);
  assert.equal(f.canvas.lowerCanvasEl.style.visibility,'');
  assert.ok(f.records.some(([kind,r])=>kind==='phase'&&r.state==='failed'));
  f.owner.reset('unavailable');
  assert.equal(f.owner.warmDocumentCaches(),false);
  assert.equal(f.frames.size,0);
});

test('alpha-image raster scaling is removed from GPU geometry, never translation or opacity',t=>{
  const f=fixture(t), object=f.objects[0];
  Object.assign(object.kloudy,{alpha_mesh_image:true,render_scale:.125});
  object.opacity=.4;
  // A composed transform includes rotation, skew, mirroring and parent scaling.
  object.calcTransformMatrix=()=>[-.25,.375,.5,.625,123,-456];
  assert.ok(f.owner.hybridRenderNow());
  assert.deepEqual([...object.__kloudyHybridRenderState.world],[-2,3,0,4,5,0,123,-456,1]);
  assert.equal(object.opacity,.4);
  assert.equal(object.kloudy.render_scale,.125);
  assert.ok(f.owner.hybridRenderNow());
  assert.deepEqual([...object.__kloudyHybridRenderState.world],[-2,3,0,4,5,0,123,-456,1],'repeated frames must not accumulate scaling');
  object.kloudy.alpha_mesh_image=false;
  assert.ok(f.owner.hybridRenderNow());
  assert.deepEqual([...object.__kloudyHybridRenderState.world],[-.25,.375,0,.5,.625,0,123,-456,1],'ordinary geometry is unchanged');
});
