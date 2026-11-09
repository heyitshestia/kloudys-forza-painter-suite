const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../../../tools/livery-studio/src/web/livery-editor.mjs'),'utf8');
const between=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
const code=[between('function handoffMessage(', 'async function exportSection('),
  between('async function readCarCatalogue(', 'async function confirmCarReplacement('),
  between('function carJobValue(', 'async function switchCar(')].join('\n');
const id='d'.repeat(32),job='e'.repeat(32),car={car_id:1478,model_code:'AUD_2_SportQuattro_86'};
const layout={format:'kfps-livery-layout-v1',vehicle:car,vinyls:[{id:'save-Left',name:'Saved Left',shapes:[{type:1048677,data:[10,20,1,-1,33,.2,1],mask:true,color:[10,30,40,255],editor_group_path:[{id:'nested',name:'Group'}]}]}],placements:[{id:'placement-Left',vinylId:'save-Left',section:'Left',x:0,y:0,scaleX:1,scaleY:1,rotation:0,opacity:1,visible:true}]};
const json=value=>JSON.parse(JSON.stringify(value));
function fixture({different=false,dirty=false,choice='discard',save=true,missing=false,fetchHook,prepareHook,native=false,vinyl=false,importStale=false,startupCache=false,startupHook}={}){
  const nodes=new Map(),calls=[],opened=[],navigation=[],messages=[];
  const location=new URL('http://127.0.0.1:4567/'+'a'.repeat(43)+'/#'+(vinyl?'vinyl':'layout')+'='+id);
  const startup_session=location.href.split('#')[0];
  let cached=startupCache?{name:'Package',layout,startup_session}:null;
  location.assign=url=>navigation.push(url);
  const context=vm.createContext({URL,File,TextEncoder,JSON,Number,Map,Set,setTimeout,clearTimeout,
    config:{host_layout_handoff:true,host_vinyl_handoff:true,car_switch:true,chrome_exposed:false,handoff_car_validation:true,vehicle:different?{car_id:1,model_code:'Other'}:car,sections:[{section:'Left'}]},
    window:{location,__kfpsStudioNativeDownloads:native,history:{state:null,replaceState(_s,_t,url){location.href=new URL(url,location).href;}}},
    completedHandoffs:new Set(),handoffWorking:false,disposed:false,sourceDocumentId:'one',busy:false,
    carWorking:false,carCommitting:false,carCancelRequested:false,carJob:null,carPicked:null,carCurrent:null,carCatalogue:[],navigationAuthorized:false,
    stop:{signal:{addEventListener(){},removeEventListener(){}}},
    $:key=>{if(!nodes.has(key))nodes.set(key,{value:'',textContent:'',hidden:false,classList:{toggle(){}},showModal(){},close(){}});return nodes.get(key);},
    t:(strings,...values)=>Array.isArray(strings)?strings.reduce((out,item,i)=>out+item+(values[i]??''),''):strings,
    errorText:error=>error?.message||String(error),canPreview:()=>true,flushNumeric:()=>true,fingerprint:()=> 'revision-1',
    setBusy(value){context.busy=value;},interactionBusy:()=>context.busy,
    renderCars(){},refreshCars(){},carMessage(){},changed:()=>dirty,message:(text,error)=>messages.push({text,error}),
    async confirmCarReplacement(){calls.push('confirm');return choice;},
    async downloadProject(){calls.push('save');return save;},
    takePackageStartupHandoff(identifier){assert.equal(identifier,id);const value=cached;cached=null;if(startupHook)startupHook(context);return value;},
    async fetch(url){calls.push(url);if(fetchHook)await fetchHook(context);return {ok:true,headers:{get:()=> 'application/json'},text:async()=>JSON.stringify(vinyl?{name:'Vinyl',shapes:layout.vinyls[0].shapes}:{name:'Package',layout,startup_session})};},
    validateProject(value,vehicle){assert.deepEqual(json(value.vehicle),json(vehicle));return value;},
    serializeProject:JSON.stringify,
    async openFile(file,options){assert.equal(options.isCurrent(),true);opened.push({value:JSON.parse(await file.text()),options});return true;},
    async importFile(file,options){if(!vinyl)throw Error('Package was treated as a vinyl');if(importStale){context.sourceDocumentId='other';return;}assert.equal(options.isCurrent(),true);opened.push(JSON.parse(await file.text()));return true;},
    async api(route,body){calls.push(route);
      if(route==='cars')return {enabled:true,current:'1'.repeat(32),cars:[{car_id:1,model_code:'Other',name:'Other',id:'1'.repeat(32)},...missing?[]:[{...car,name:'Audi',id:'2'.repeat(32)}]]};
      if(route==='car-switch'){assert.deepEqual(json(body),{carId:'2'.repeat(32),layoutId:id});if(prepareHook)await prepareHook(context);return {id:job,status:'ready'};}
      if(route.endsWith('/cancel'))return {id:job,status:'cancelled'};
      if(route.endsWith('/commit'))return {id:job,status:'committed',url:location.origin+'/'+'b'.repeat(43)+'/'};
      throw Error(route);
    }
  });
  vm.runInContext(code,context);
  return {context,calls,opened,navigation,nodes,messages,run:()=>context.importHostVinyl()};
}
test('failed artwork import also replaces Ready in the main status',async()=>{
  const h=fixture();h.context.openFile=async()=>{throw Error('Not enough preview memory.');};
  await h.run();
  assert.deepEqual(h.messages,[{text:'Not enough preview memory.',error:true}]);
  assert.equal(h.context.completedHandoffs.size,0);
  assert.equal(h.nodes.get('retryHostTransfer').hidden,false);
});
for(const native of [false,true])test(`same-car package uses shared ${native?'native':'browser'} dispatcher and remains unsaved`,async()=>{
  const h=fixture({native});await h.run();assert.equal(h.opened.length,1);assert.deepEqual(h.opened[0].value,layout);
  assert.equal(h.opened[0].options.unsaved,true);assert.equal(h.context.window.location.hash,'');
  assert.match(h.nodes.get('hostTransferMessage').textContent,/paint.*materials/i);
});
test('startup layout cache skips second fetch and keeps normal adoption checks',async()=>{
  const h=fixture({startupCache:true});await h.run();
  assert.equal(h.calls.some(route=>route.startsWith('./api/host-')),false);
  assert.equal(h.calls.includes('confirm'),true);
  assert.equal(h.opened.length,1);
  assert.equal(h.opened[0].options.unsaved,true);
  assert.deepEqual(h.opened[0].value,layout);
});
test('cached startup layout still rejects stale document and dirty cancellation',async()=>{
  const stale=fixture({startupCache:true,startupHook:ctx=>{ctx.sourceDocumentId='other';}});
  await stale.run();assert.equal(stale.opened.length,0);assert.equal(stale.context.completedHandoffs.size,0);
  const dirty=fixture({startupCache:true,dirty:true,choice:'cancel'});
  await dirty.run();assert.equal(dirty.opened.length,0);assert.equal(dirty.context.completedHandoffs.size,0);
  await dirty.run();assert.equal(dirty.calls.includes('./api/host-layout/'+id),true);
});
for(const [choice,save] of [['cancel',true],['save',false]])test(`native dirty ${choice}/${save} retains document and car`,async()=>{
  const h=fixture({native:true,dirty:true,different:true,choice,save});await h.run();assert.equal(h.opened.length,0);assert.equal(h.navigation.length,0);
  assert.equal(h.calls.includes('confirm'),true);
  assert.equal(h.calls.includes('car-switch'),false);
});
test('native save completes before exact-car preparation and fragment survives token rotation',async()=>{
  const h=fixture({native:true,dirty:true,different:true,choice:'save'});await h.run();assert.equal(h.navigation.length,1);
  assert.ok(h.calls.indexOf('save')<h.calls.indexOf('car-switch'));assert.ok(h.navigation[0].endsWith('#layout='+id));
  assert.equal(h.context.completedHandoffs.size,0);assert.equal(h.opened.length,0);
});
test('missing exact car never starts preparation',async()=>{
  const h=fixture({native:true,different:true,missing:true});await h.run();assert.equal(h.calls.includes('car-switch'),false);assert.equal(h.opened.length,0);
  assert.equal(h.calls.includes('cars'),true);
});
test('cancel during preparation never commits or replaces',async()=>{
  const h=fixture({native:true,different:true,prepareHook:ctx=>{ctx.carCancelRequested=true;}});await h.run();
  assert.equal(h.navigation.length,0);assert.equal(h.calls.some(route=>route.endsWith('/commit')),false);assert.equal(h.opened.length,0);
  assert.equal(h.calls.some(route=>route.endsWith('/cancel')),true);
});
test('late document change cannot replace the active layout',async()=>{
  const h=fixture({fetchHook:ctx=>{ctx.sourceDocumentId='other';}});await h.run();assert.equal(h.opened.length,0);assert.equal(h.navigation.length,0);
});
test('malformed transfer fragments never fetch',async()=>{
  const h=fixture();h.context.window.location.hash='#layout=../../save';await h.run();assert.equal(h.calls.length,0);
});
test('existing vinyl fragment stays on its original import route',async()=>{
  const h=fixture({vinyl:true});await h.run();assert.equal(h.opened.length,1);
  assert.deepEqual(h.opened[0].shapes,layout.vinyls[0].shapes);assert.equal(h.context.completedHandoffs.size,1);
  assert.equal(h.calls.includes('./api/host-vinyl/'+id),true);
});
test('stale vinyl adoption is not falsely marked completed',async()=>{
  const h=fixture({vinyl:true,importStale:true});await h.run();assert.equal(h.opened.length,0);
  assert.equal(h.context.completedHandoffs.size,0);assert.equal(h.context.window.location.hash,'#vinyl='+id);
});
for(const dirty of [false,true])test(`Chrome different-car package rejects before confirmation or car APIs (dirty=${dirty})`,async()=>{
  const h=fixture({different:true,dirty,choice:'save'});await h.run();
  assert.deepEqual(h.calls,['./api/host-layout/'+id]);assert.equal(h.opened.length,0);assert.equal(h.navigation.length,0);
  assert.equal(h.context.completedHandoffs.size,0);assert.equal(h.context.window.location.hash,'#layout='+id);
  assert.equal(h.nodes.get('hostTransferMessage').textContent,"In Chrome, save your work and choose this package's car in Studio before opening it. Automatic car switching could interrupt another Studio window.");
});
test('same-car Chrome package still honors dirty cancellation',async()=>{
  const h=fixture({dirty:true,choice:'cancel'});await h.run();assert.equal(h.opened.length,0);
  assert.equal(h.calls.includes('confirm'),true);assert.equal(h.calls.includes('car-switch'),false);
  assert.equal(h.context.completedHandoffs.size,0);
});
