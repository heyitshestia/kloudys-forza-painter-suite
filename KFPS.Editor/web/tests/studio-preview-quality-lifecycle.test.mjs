import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as policy from '../../../tools/livery-studio/src/web/preview-quality.mjs';
import {placementMatrix,sectionToPaint,createHistory} from '../../../tools/livery-studio/src/web/layout-model.mjs';

const editorSource=readFileSync(new URL('../../../tools/livery-studio/src/web/livery-editor.mjs',import.meta.url),'utf8');
const sceneSource=readFileSync(new URL('../../../tools/livery-studio/src/web/livery-scene.js',import.meta.url),'utf8');
const compositeSource=readFileSync(new URL('../../../tools/livery-studio/src/web/vinyl-compositing.mjs',import.meta.url),'utf8');
const MiB=1024**2;
const paintSize=[2048,892];

// Execute product functions, replacing only browser/GPU boundaries. No pixels,
// server, preferences, files or real graphics resources are created by this suite.
function between(source,start,end) {
  const first=source.indexOf(start),last=source.indexOf(end,first+start.length);
  assert.ok(first>=0&&last>first,`Product source boundary moved: ${start}`);
  return source.slice(first,last).replace(/^export /gm,'');
}

class Texture {
  constructor(image,mipmaps=true) {
    this.image=image;this.isTexture=true;this.generateMipmaps=mipmaps;this.disposed=false;
  }
  dispose(){this.disposed=true;}
}

function sceneHarness() {
  const original=new Texture({width:paintSize[0],height:paintSize[1]});
  const sharedBuffer={byteLength:20*MiB};
  const context=vm.createContext({
    ...policy,editorPaintTexture:null,editorCanvasBytes:0,viewerDisposed:false,modelReady:true,
    renderContract:{paint_size:paintSize},graphicsDevice:{maxTextureSize:16384,anisotropy:4},
    trackedTextures:new Set([original,new Texture({width:4096,height:4096},false),
      new Texture({width:2048,height:4096},false)]),
    trackedGeometries:new Set([{attributes:{position:{array:{buffer:sharedBuffer}},
      normal:{array:{buffer:sharedBuffer}}},index:null}]),
    paintMaterials:[{uniforms:{paintMap:{value:original}}}],glassMaterials:[],
    THREE:{CanvasTexture:Texture,SRGBColorSpace:'srgb'},
    gl:{NO_ERROR:0,isContextLost:()=>false,getError:()=>0},
    renderer:{initTexture(){},setPixelRatio(){},setSize(){}},requestRender(){},
    viewport:{clientWidth:320,clientHeight:200},window:{devicePixelRatio:1},
    navigator:{deviceMemory:2},gpuBudgetBytes:1024*MiB,modelResourceBytes:0,
    renderWidth:0,renderHeight:0,renderPixelRatio:0,modelBounds:null,
    homeCamera:{clone:()=>({sub:()=>({})})},homeTarget:{},camera:{updateProjectionMatrix(){}},
  });
  vm.runInContext([
    between(sceneSource,'export function updatePaintCanvas(','export function isSceneReady('),
    between(sceneSource,'function resourceBytes()','function trackMaterial('),
    between(sceneSource,'function resize()','function renderFrame('),
  ].join('\n'),context);
  const bytes=context.resourceBytes();
  context.modelResourceBytes=bytes.geometry+bytes.textures;
  context.resize();
  return context;
}

function editorHarness(scene=sceneHarness()) {
  const writes=[],nodes=new Map(),listeners=new Map();
  const canvas=()=>{
    const value={};
    for(const key of ['width','height']) {
      let size=1;
      Object.defineProperty(value,key,{get:()=>size,set:next=>{size=next;writes.push([key,next]);}});
    }
    return value;
  };
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',classList:{toggle(){}},append(){},addEventListener(){}});
    return nodes.get(id);
  };
  const config={paint_size:paintSize,vehicle:{car_id:1},sections:Array.from({length:10},(_,i)=>({section:`S${i}`}))};
  const context=vm.createContext({
    ...policy,AbortController,setTimeout,clearTimeout,queueMicrotask,stop:new AbortController(),
    config,project:{vinyls:[],placements:[]},activeQuality:'balanced',disposed:false,
    images:new Map(),sources:new Map(),sectionCanvases:new Map(),atlas:canvas(),sectionCanvas:canvas(),
    navigator:{deviceMemory:8},$:node,t:value=>value,errorText:value=>value,
    diagnostics:{emit(){}},sceneState:()=>({device:scene.graphicsDevice,bytes:scene.resourceBytes()}),
    fetch:async()=>({ok:true,json:async()=>({version:1,quality:'sharp'})}),
    document:{createElement:tag=>tag==='canvas'?canvas():{}},
    window:{addEventListener:(event,handler)=>listeners.set(event,handler),removeEventListener(){}},
    projectStorage:null,confirmations:null,nativeDownloads:new Map(),surface:null,tools:null,
    inspection:null,recovery:null,queued:0,transform:null,drag:null,
    sourceButtons:new Map(),placementButtons:new Map(),saved:'',
    sceneReady:Promise.resolve(),isSceneReady:()=>!scene.viewerDisposed,
    emptyProject:()=>({vinyls:[],placements:[]}),fingerprint:()=>'',sectionLabel:value=>value,
    getBounds(){},hitPlacement(){},selectPlacement(){},previewTransform(){},message(){},
    showPlacementStack(){},componentSelectionChanged(){},
  });
  vm.runInContext(compositeSource.replace(/^import[^\n]*\n/gm,'').replace(/^export /gm,''),context);
  vm.runInContext(between(editorSource,'async function api(','function drawSection('),context);
  vm.runInContext(between(editorSource,'function drawThumbnail(','function artworkButton('),context);
  return {context,writes,listeners,config,scene};
}

test('startup capacity retains the live atlas in the old/new GPU peak',async()=>{
  const {context,scene}=editorHarness();
  const checks=[];
  context.checkPreviewQuality=options=>{
    const result=policy.checkPreviewQuality(options);
    checks.push({options,result});return result;
  };
  const liveBytes=scene.resourceBytes().estimatedGpu;
  assert.ok(liveBytes>0);
  await context.initializePreviewQuality();
  assert.ok(checks.length,'Startup must invoke the real capacity policy');
  for(const {options,result} of checks) {
    assert.ok(options.sceneBytes>=liveBytes,'Startup subtracted a still-live texture before replacement');
    assert.ok(result.peakGpu>=liveBytes+result.gpu,'Startup omitted old/new allocation overlap');
  }
});

test('quality refresh reuses thumbnail controls and resets their old image recordings',()=>{
  const {context}=editorHarness();
  const canvases=[];
  const canvas=()=>{
    let width=100,resets=0,draws=0;
    const value={height:72,getContext:()=>({clearRect(){},drawImage(){draws++;}})};
    Object.defineProperty(value,'width',{get:()=>width,set:next=>{width=next;resets++;}});
    canvases.push({value,state:()=>({resets,draws})});return value;
  };
  const image={width:4096,height:2048,artworkBounds:[100,200,1800,900]};
  const source=canvas(),placement=canvas(),preview=canvas();
  const button=target=>({querySelector:()=>target});
  const sourceButton=button(source),placementButton=button(placement);
  context.images.set('v1',image);context.pickedSource='v1';
  context.sourceButtons.set('v1',sourceButton);context.placementButtons.set('p1',placementButton);
  context.project.placements=[{id:'p1',vinylId:'v1'}];
  context.$=()=>preview;
  context.refreshPreviewThumbnails();
  assert.equal(context.sourceButtons.get('v1'),sourceButton);
  assert.equal(context.placementButtons.get('p1'),placementButton);
  for(const item of canvases)assert.deepEqual(item.state(),{resets:1,draws:1});
  context.drawThumbnail(preview,image);
  assert.deepEqual(canvases[2].state(),{resets:1,draws:2},'Ordinary refresh must not reallocate thumbnails');
  context.releaseArtworkButtons(context.sourceButtons);
  context.releaseArtworkButtons(context.placementButtons);
  for(const item of [source,placement])assert.deepEqual([item.width,item.height],[1,1]);
});

test('preview rasters have explicit disposal on rejection, closure and replacement',async()=>{
  for(const outcome of ['accepted','wrong-size','closed']){
    const {context}=editorHarness();let closes=0;
    const image={width:outcome==='wrong-size'?1:1024,height:512,close(){closes++;}};
    context.atob=atob;context.Blob=Blob;
    context.api=async()=>({png:'data:image/png;base64,AQID',bounds:[10,20,30,40]});
    context.requireQualityCapacity=()=>{};
    context.createImageBitmap=async blob=>{
      assert.deepEqual([...new Uint8Array(await blob.arrayBuffer())],[1,2,3]);
      if(outcome==='closed')context.disposed=true;
      return image;
    };
    if(outcome==='accepted'){
      assert.equal(await context.raster([],'fast'),image);
      assert.deepEqual(image.artworkBounds,[10,20,30,40]);assert.equal(closes,0);
      const rasters=new Map([['v1',image]]);
      context.releasePreview(rasters,new Map(),null);
      assert.equal(rasters.size,0);
    }else await assert.rejects(context.raster([],'fast'),outcome==='closed'?/closed/:/dimensions/);
    assert.equal(closes,1);
  }
});

test('an already closed editor cannot start a timed render request',async()=>{
  const {context}=editorHarness();let requests=0;
  context.fetch=async()=>{requests++;return {ok:true,json:async()=>({})};};
  context.stop.abort();
  await assert.rejects(context.api('render-vinyl',{shapes:[]},60000),/closed|abort/i);
  assert.equal(requests,0);
});

test('import closes an unadopted bitmap when placement or project validation rejects',async()=>{
  for(const failure of ['placement','project']){
    const {context}=editorHarness();let closes=0;
    Object.assign(context,{MAX_VINYLS:96,MAX_PLACEMENTS:500,crypto:{randomUUID:()=> 'v1'},
      requirePreview(){},snapshot:()=>({}),api:async()=>({shapes:[{}]}),raster:async()=>({close(){closes++;}}),
      createPlacement(){if(failure==='placement')throw Error('placement rejected');return {id:'p1'};},
      serializeProject(){throw Error('project rejected');}});
    vm.runInContext(between(editorSource,'async function importFile(','async function confirmReplace('),context);
    await assert.rejects(context.importFile({name:'test.json',size:40,text:async()=>'{"shapes":[{}]}'}),/rejected/);
    assert.equal(closes,1);
    assert.equal(context.images.size,0);
    assert.equal(context.project.vinyls.length,0);
  }
});

test('texture replacement and canvas-count changes refresh the existing resize budget',()=>{
  const context=sceneHarness();
  const allocation=policy.previewFootprint({quality:'sharp',paintSize,sources:1,sections:1});
  const paint={width:allocation.paint[0],height:allocation.paint[1]};
  // Derive the test budget through the real texture loop, not a second estimator.
  const extra=new Texture(paint),before=context.resourceBytes();
  context.trackedTextures.add(extra);
  const uploadBytes=context.resourceBytes().textures-before.textures;
  context.trackedTextures.delete(extra);
  context.gpuBudgetBytes=context.modelResourceBytes+uploadBytes*2+allocation.canvasGpu;
  const resizeAndCheck=()=>{
    context.viewport.clientWidth=4096;context.viewport.clientHeight=2160;context.resize();
    const bytes=context.resourceBytes();
    assert.ok(bytes.estimatedGpu+context.editorCanvasBytes<=bytes.budget+1,
      'Resizing exceeded the budget after texture/canvas allocation changed');
    assert.equal(context.modelResourceBytes,bytes.geometry+bytes.textures+context.editorCanvasBytes,
      'Resize must use the existing resourceBytes texture loop plus canvas allocations');
  };
  resizeAndCheck();
  context.viewport.clientWidth=320;context.viewport.clientHeight=200;context.resize();
  context.updatePaintCanvas(paint,'sharp',allocation.canvasGpu);
  resizeAndCheck();
  const texture=context.editorPaintTexture;
  const larger=policy.previewFootprint({quality:'sharp',paintSize,sources:1,sections:2});
  context.updatePaintCanvas(paint,'sharp',larger.canvasGpu);
  assert.equal(context.editorPaintTexture,texture,'Canvas accounting must not recreate an unchanged texture');
  resizeAndCheck();
});

test('replacing paint still disposes the prior texture when no materials reference it',()=>{
  const context=sceneHarness();
  context.updatePaintCanvas({width:2048,height:892});
  const previous=context.editorPaintTexture;
  context.paintMaterials=[];context.glassMaterials=[];
  context.updatePaintCanvas({width:1024,height:446},'fast');
  assert.equal(previous.disposed,true);
  assert.equal(context.trackedTextures.has(previous),false);
});

test('pagehide during the preference read cannot allocate or initialize after cleanup',{timeout:2000},async()=>{
  const {context,writes,listeners,config,scene}=editorHarness();
  let began,initializations=0;
  const pending=new Promise(resolve=>{began=resolve;});
  context.fetch=async(url,{signal})=>{
    if(url.endsWith('/editor-config'))return {ok:true,json:async()=>config};
    assert.ok(url.endsWith('/preview-quality'));
    return new Promise((_resolve,reject)=>{
      signal.addEventListener('abort',()=>reject(Object.assign(Error('Aborted'),{name:'AbortError'})),{once:true});
      began();
    });
  };
  const unexpectedInitialization=Error('Editor initialization resumed after pagehide');
  context.createSurfaceEditor=()=>{initializations++;throw unexpectedInitialization;};
  vm.runInContext([
    between(editorSource,'async function initialize()','function componentSelectionChanged('),
    between(editorSource,"window.addEventListener('pagehide',","initialize().catch("),
  ].join('\n'),context);
  const boot=context.initialize().then(()=>null,error=>error);
  await pending;
  scene.viewerDisposed=true;
  listeners.get('pagehide')();
  const cleanedWrites=writes.length;
  assert.deepEqual([context.atlas.width,context.atlas.height,context.sectionCanvas.width,context.sectionCanvas.height],[1,1,1,1]);
  const error=await boot;
  if(error&&error!==unexpectedInitialization&&error.name!=='AbortError'&&error.message!=='The editor is closed.')throw error;
  assert.deepEqual({allocationsAfterCleanup:writes.length-cleanedWrites,initializations},
    {allocationsAfterCleanup:0,initializations:0},'An aborted startup must stay disposed');
});

test('scheduled section growth rejects before painting and retries without transient cache growth',()=>{
  const {context,scene}=editorHarness();
  const events=[],frames=[],checks=[];
  let sequence=0,clock=0,paintCalls=0,uploads=0,allocations=0,atlasChanges=0,errorStatus=false;
  const size=policy.previewQuality(context.activeQuality).size;
  const canvas=(name,width=size[0],height=size[1])=>{
    const value={name};
    for(const [key,initial] of [['width',width],['height',height]]) {
      let dimension=initial;
      Object.defineProperty(value,key,{get:()=>dimension,set:next=>{
        dimension=next;events.push(`resize:${name}:${key}`);
      }});
    }
    const drawing={};
    for(const method of ['save','restore','setTransform','clearRect','beginPath','rect','clip','drawImage']) {
      drawing[method]=()=>{if(name==='atlas'&&(method==='clearRect'||method==='drawImage'))atlasChanges++;};
    }
    value.getContext=()=>drawing;
    return value;
  };
  const old=canvas('obsolete'),kept=canvas('kept'),atlas=canvas('atlas',...paintSize);
  context.atlas=atlas;
  context.sectionCanvases=new Map([['S9',old],['S1',kept]]);
  context.images=new Map([['reused',{}],['undo-only',{}]]);
  const placement=(id,section,extra={})=>({id,section,vinylId:'reused',visible:true,opacity:1,
    x:0,y:0,scaleX:1,scaleY:1,rotation:0,...extra});
  context.project={vinyls:[{id:'reused'}],placements:[placement('new','S0'),placement('duplicate','S0'),
    placement('kept','S1'),placement('hidden','S2',{visible:false}),placement('transparent','S3',{opacity:0})]};
  // Put the new section before the obsolete one to expose allocation-before-release.
  context.config.sections=['S0','S1','S2','S3','S9'].map((section,index)=>({section,
    atlasToLocal:[1,0,0,0,1,0],source_region:[0,0,1,1],paint_region:[index/5,0,(index+1)/5,1]}));
  context.dirtySections=new Set(context.config.sections.map(section=>section.section));
  context.history=createHistory();
  context.history.push({vinylIds:['undo-only']},{vinylIds:['reused']});
  context.metrics={paintUpdates:3,lastComposeMs:1,maxComposeMs:1};
  context.previewAllocationBlocked=false;
  context.canPreview=()=>true;
  context.performance={now:()=>++clock};
  context.requestAnimationFrame=callback=>{frames.push(callback);return ++sequence;};
  context.drawSelection=()=>events.push('selection');
  context.updatePaintCanvas=(source,quality,bytes)=>{
    assert.equal(source,atlas);assert.equal(quality,context.activeQuality);assert.ok(bytes>0);
    uploads++;events.push('upload');
  };
  context.document.createElement=tag=>{
    assert.equal(tag,'canvas');
    assert.equal(context.sectionCanvases.has('S9'),false,'Remove the obsolete cache entry before allocation');
    assert.deepEqual([old.width,old.height],[1,1],'Release the obsolete surface before allocation');
    allocations++;events.push('allocate');return canvas('new');
  };
  context.placementMatrix=placementMatrix;context.sectionToPaint=sectionToPaint;
  const status=context.$('previewQualityStatus');
  status.classList.toggle=(_name,enabled)=>{errorStatus=enabled;};
  const requireCapacity=context.requireQualityCapacity;
  context.requireQualityCapacity=(quality,count,options)=>{
    checks.push({quality,count,sections:options.sections});events.push('capacity');
    return requireCapacity(quality,count,options);
  };
  vm.runInContext([
    between(editorSource,'function drawSection(','function drawSelection('),
    between(editorSource,'function schedule()','function drawThumbnail('),
  ].join('\n'),context);
  const paint=context.paintSection;
  context.paintSection=(...args)=>{paintCalls++;events.push('paint');return paint(...args);};
  const runFrame=()=>{
    context.schedule();assert.equal(frames.length,1);frames.shift()();assert.equal(context.queued,0);
  };
  const projectBefore=JSON.stringify(context.project),dirtyBefore=[...context.dirtySections];
  const historyState=()=>({undo:context.history.canUndo,redo:context.history.canRedo,
    retained:[...context.history.retainedVinylIds()].sort()});
  const historyBefore=historyState(),metricsBefore={...context.metrics};
  scene.gpuBudgetBytes=1;
  runFrame();
  assert.deepEqual(checks,[{quality:context.activeQuality,count:context.images.size,sections:2}],
    'Count unique visible, positive-opacity sections and all retained source images');
  assert.deepEqual({paintCalls,uploads,allocations,atlasChanges},{paintCalls:0,uploads:0,allocations:0,atlasChanges:0});
  assert.deepEqual([...context.sectionCanvases],[['S9',old],['S1',kept]]);
  assert.deepEqual([old.width,old.height],size);
  assert.deepEqual([...context.dirtySections],dirtyBefore,'Keep dirty sections available for retry');
  assert.deepEqual({...context.metrics},metricsBefore);
  assert.equal(context.atlas,atlas);assert.equal(context.previewAllocationBlocked,true);
  assert.ok(status.textContent);assert.equal(errorStatus,true);
  assert.equal(JSON.stringify(context.project),projectBefore);assert.deepEqual(historyState(),historyBefore);

  scene.gpuBudgetBytes=1024*MiB;
  runFrame();
  assert.equal(checks.length,2);assert.equal(allocations,1);assert.equal(uploads,1);assert.ok(atlasChanges>0);
  assert.ok(events.indexOf('resize:obsolete:width')<events.indexOf('allocate'));
  assert.ok(events.indexOf('resize:obsolete:height')<events.indexOf('allocate'));
  assert.deepEqual([...context.sectionCanvases.keys()].sort(),['S0','S1']);
  assert.equal(context.sectionCanvases.get('S1'),kept);
  assert.equal(context.dirtySections.size,0);assert.equal(context.previewAllocationBlocked,false);
  assert.equal(status.textContent,'');assert.equal(errorStatus,false);
  assert.equal(context.metrics.paintUpdates,metricsBefore.paintUpdates+1);
  assert.equal(JSON.stringify(context.project),projectBefore);assert.deepEqual(historyState(),historyBefore);

  context.sceneState=()=>{throw Error('Cached section drag invoked the full scene estimator');};
  context.project.placements[0].x++;
  context.dirtySections.add('S0');
  runFrame();
  assert.equal(checks.length,2);assert.equal(allocations,1);assert.equal(uploads,2);
  assert.equal(context.dirtySections.size,0);
});
