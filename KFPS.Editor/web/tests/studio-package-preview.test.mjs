import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as policy from '../../../tools/livery-studio/src/web/preview-quality.mjs';
import {hasMasks,maskImageCount,closeVinylPreview} from '../../../tools/livery-studio/src/web/vinyl-compositing.mjs';

const source=readFileSync(new URL('../../../tools/livery-studio/src/web/livery-editor.mjs',import.meta.url),'utf8');
function between(start,end){
  const first=source.indexOf(start),last=source.indexOf(end,first+start.length);
  assert.ok(first>=0&&last>first);return source.slice(first,last);
}

// Run the real loader, raster admission and capacity policy; replace only IO,
// graphics resources, and unrelated document/UI services.
function fixture({quality='sharp',count=10,masks=0,budget=512*1024**2,failAt=0,staleAt=0}={}){
  const rendered=[],closed=[],checks=[],painted=[],nodes=new Map(),canvases=[],messages=[],events=[];
  let current=true,parts={RearWing:12};
  const canvas=()=>{const value={width:1,height:1,getContext:()=>({})};canvases.push(value);return value;};
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:quality,textContent:'',classList:{toggle(){}}});return nodes.get(id);};
  const next={vehicle:{car_id:1,model_code:'Test'},vehicle_parts:{RearWing:34},
    vinyls:Array.from({length:count},(_,i)=>({id:`v${i}`,shapes:[{id:i,mask:i<masks,group:[1,2]}]})),
    placements:Array.from({length:count},(_,i)=>({id:`p${i}`,vinylId:`v${i}`,section:`S${i}`,visible:true,opacity:1,x:i,y:0-i}))};
  const old={vehicle:next.vehicle,vinyls:[{id:'old',shapes:[]}],placements:[]};
  const oldImage={close:()=>closed.push('old')};
  const context=vm.createContext({...policy,hasMasks,maskImageCount,closeVinylPreview,File,JSON,Map,crypto,
    AbortController,stop:new AbortController(),navigator:{deviceMemory:8},disposed:false,
    config:{vehicle:next.vehicle,paint_size:[2048,1203],sections:next.placements.map(p=>({section:p.section}))},
    sceneState:()=>({device:{maxTextureSize:16384},bytes:{estimatedGpu:64*1024**2,budget}}),
    document:{createElement:canvas},$:node,t:value=>value,errorText:error=>String(error?.message||error),
    requirePreview(){},validateProject:value=>value,validatePartConfiguration:value=>value,serializeProject:JSON.stringify,
    activeQuality:quality,project:old,images:new Map([['old',oldImage]]),sources:new Map([['old',old.vinyls[0]]]),
    sectionCanvases:new Map(),atlas:canvas(),sectionCanvas:canvas(),dirtySections:new Set(),metrics:{paintUpdates:0},
    async api(route,value){
      assert.equal(route,'render-vinyl','Opening must not persist a quality preference');
      rendered.push(value);if(rendered.length===staleAt)current=false;
      if(rendered.length===failAt)throw Error('render failed');return value;
    },
    async decodeVinylPreview(result,q,masked){const id=result.shapes[0].id;
      return {close:()=>closed.push(id),...(masked?{maskCoverage:{close:()=>closed.push(`mask${id}`)}}:{})};},
    currentVehicleParts:()=>({...parts}),setVehicleParts:value=>{parts=value;},retainParts(){},
    paintSection(section,q,cache,images,target,document){
      assert.equal(document.vinyls.length,count);painted.push(section.section);cache.set(section.section,canvas());
    },
    updatePaintCanvas(){},refreshPreviewThumbnails(){},drawSelection(){},surface:null,
    sourceSignature:'',placementSignature:'',selected:null,pickedSource:null,selectedIds:[],sourceDocumentId:'old',
    current:()=>null,authoring:{selectionIds:()=>[]},sourceMonitor:{stop(){}},history:{reset(){}},saved:'old',
    fingerprint:()=> 'new',markAll(){},refresh(){},projectStorage:{adopt(){}},recovery:{changed(){}},
    message:text=>messages.push(text),diagnostics:{emit:(...args)=>events.push(args)},projectCounts:()=>({}),
  });
  vm.runInContext(between('function qualityStatus(','async function changePreviewQuality('),context);
  vm.runInContext(between('async function openFile(','function nativeDownloadFinished('),context);
  const check=context.qualityCapacity;
  context.qualityCapacity=(...args)=>{const result=check(...args);checks.push({args,result});return result;};
  return {context,next,old,oldImage,rendered,closed,checks,painted,nodes,canvases,messages,events,
    parts:()=>parts,stale:()=>{current=false;},run:()=>context.openFile(new File([JSON.stringify(next)],'test.json'),{isCurrent:()=>current,unsaved:true})};
}

test('ten-section Sharp package opens at a safe temporary quality with every shape unchanged',async()=>{
  const h=fixture();assert.equal(await h.run(),true);
  assert.equal(h.context.activeQuality,'balanced');assert.equal(h.rendered.length,10);
  assert.ok(h.rendered.every(r=>r.preview_quality==='balanced'));
  assert.deepEqual(JSON.parse(JSON.stringify(h.context.project)),h.next);
  assert.equal(h.context.images.size,10);assert.equal(h.painted.length,10);
  assert.equal(h.nodes.get('previewQuality').value,'balanced');
  assert.match(h.nodes.get('previewQualityStatus').textContent,/preference.*exports.*unchanged/i);
  assert.deepEqual(h.closed,['old']);assert.equal(h.context.saved,'');
  assert.ok(h.checks.some(c=>c.args[0]==='sharp'&&!c.result.allowed));
  assert.ok(h.checks.filter(c=>c.args[0]==='balanced').length>=2,'Recheck peak after asynchronous renders');
});

test('Fast stays Fast and masks are included in whole-document admission',async()=>{
  const h=fixture({quality:'fast',masks:10});await h.run();
  assert.equal(h.context.activeQuality,'fast');
  assert.ok(h.checks.every(c=>c.args[2].masks===10&&c.args[2].sections===10&&c.args[2].staging===true));
  assert.ok(h.rendered.every(r=>r.preview_quality==='fast'));
});

test('a small Sharp project keeps its requested preview detail',async()=>{
  const h=fixture({count:1});await h.run();assert.equal(h.context.activeQuality,'sharp');
  assert.equal(h.rendered[0].preview_quality,'sharp');
});

test('no fitting quality rejects before rendering and retains the current document',async()=>{
  const h=fixture({budget:1});await assert.rejects(h.run(),/memory/);
  assert.equal(h.rendered.length,0);assert.equal(h.context.project,h.old);
  assert.equal(h.context.images.get('old'),h.oldImage);assert.deepEqual(h.closed,[]);
});

for(const mode of ['render','stale','parts','upload','capacity'])test(`${mode} failure retains the old layout, quality and component selection`,async()=>{
  const h=fixture({failAt:mode==='render'?3:0,staleAt:mode==='stale'?3:0});
  if(mode==='upload')h.context.updatePaintCanvas=()=>{throw Error('upload failed');};
  if(mode==='parts'){
    const set=h.context.setVehicleParts;let first=true;
    h.context.setVehicleParts=value=>{set(value);if(first){first=false;throw Error('parts failed');}};
  }
  if(mode==='capacity'){
    const check=h.context.qualityCapacity;
    h.context.qualityCapacity=(...args)=>h.rendered.length?{allowed:false,reason:'memory'}:check(...args);
  }
  await assert.rejects(h.run(),/failed|Nothing was opened|memory/);
  assert.equal(h.context.project,h.old);assert.equal(h.context.activeQuality,'sharp');
  assert.equal(h.context.images.get('old'),h.oldImage);assert.ok(!h.closed.includes('old'));
  assert.deepEqual(h.parts(),{RearWing:12});
  assert.equal(h.closed.length,h.rendered.length-Number(mode==='render'));
  for(const canvas of h.canvases.slice(2))assert.deepEqual([canvas.width,canvas.height],[1,1]);
});
