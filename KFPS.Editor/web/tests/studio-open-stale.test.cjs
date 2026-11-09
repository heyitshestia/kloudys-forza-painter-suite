const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../../../tools/livery-studio/src/web/livery-editor.mjs'),'utf8');
const start=source.indexOf('async function openFile(');
const code=source.slice(start,source.indexOf('function nativeDownloadFinished(',start));
function fixture({count=3,staleAt=Infinity,disposed=false}={}){
  const calls=[],closed=[],old={id:'old'},next={vehicle:{car_id:1,model_code:'Test'},vinyls:Array.from({length:count},(_,id)=>({id:String(id),shapes:[id]})),placements:[]};
  let current=true;
  const canvas=()=>({width:1,height:1,getContext:()=>({})});
  const context=vm.createContext({File,JSON,Map,crypto,structuredClone,
    requirePreview(){calls.push('preview');},validateProject:value=>value,validatePartConfiguration:()=>({}),serializeProject:JSON.stringify,
    config:{vehicle:next.vehicle,sections:[{section:'Top'}]},activeQuality:'balanced',maskImageCount:()=>0,sectionCanvases:new Map(),previewSectionCount:()=>1,
    hasMasks:()=>false,qualityCapacity:()=>({allowed:true}),requireQualityCapacity:()=>({paint:[2,1],canvasGpu:1}),
    document:{createElement:canvas},currentVehicleParts:()=>({}),paintSection(){},updatePaintCanvas(){},
    atlas:canvas(),sectionCanvas:canvas(),previewQuality:()=>({size:[2,1]}),$:()=>({}),dirtySections:new Set(),metrics:{paintUpdates:0},drawSelection(){},surface:null,
    releasePreview(images,sections,paint){for(const image of images.values())closed.push(image.id);images.clear();sections.clear();paint.width=paint.height=1;},
    async raster(shapes){calls.push('raster');if(calls.filter(v=>v==='raster').length===staleAt)current=false;return {id:shapes[0]};},
    closeVinylPreview:value=>closed.push(value.id),disposed,setVehicleParts(){calls.push('parts');},project:old,images:new Map([['old',old]]),sources:new Map(),
    sourceSignature:'',placementSignature:'',selected:null,pickedSource:null,selectedIds:[],sourceDocumentId:'old',
    current:()=>null,retainParts(){},authoring:{selectionIds:()=>[]},sourceMonitor:{stop(){}},history:{reset(){}},saved:'old',
    fingerprint:()=> 'new',markAll(){},refresh(){},projectStorage:{adopt(){}},recovery:{changed(){}},message(){},diagnostics:{emit(){}},projectCounts:()=>({}),
  });
  vm.runInContext(code,context);
  return {context,calls,closed,old,next,stale:()=>{current=false;},run:()=>context.openFile(new File([JSON.stringify(next)],'test.json'),{isCurrent:()=>current})};
}
test('already superseded package does not rasterize or touch current document',async()=>{
  const h=fixture();h.stale();await assert.rejects(h.run(),/Nothing was opened/);
  assert(!h.calls.includes('raster'));assert.equal(h.context.project,h.old);assert.deepEqual(h.closed,[]);
});
test('superseded during rasterization stops before next source and releases only staged previews',async()=>{
  const h=fixture({staleAt:1});await assert.rejects(h.run(),/Nothing was opened/);
  assert.equal(h.calls.filter(v=>v==='raster').length,1);assert.deepEqual(h.closed,[0]);
  assert.equal(h.context.project,h.old);assert(!h.calls.includes('parts'));assert(h.context.images.has('old'));
});
test('superseded at the last source cannot commit and releases every staged preview',async()=>{
  const h=fixture({staleAt:3});await assert.rejects(h.run(),/Nothing was opened/);
  assert.deepEqual(h.closed,[0,1,2]);assert.equal(h.context.project,h.old);assert(!h.calls.includes('parts'));
});
test('closed editor does not start work',async()=>{
  const h=fixture({disposed:true});await assert.rejects(h.run(),/editor is closed/);assert(!h.calls.includes('raster'));
});
test('current package commits all previews atomically and frees the old preview',async()=>{
  const h=fixture();assert.equal(await h.run(),true);assert.deepEqual(JSON.parse(JSON.stringify(h.context.project)),h.next);
  assert.deepEqual(h.closed,['old']);assert.equal(h.context.images.size,3);assert(h.calls.includes('parts'));
});
