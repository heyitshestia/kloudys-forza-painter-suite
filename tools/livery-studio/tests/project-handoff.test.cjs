const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src/web/livery-editor.mjs'),'utf8');
const between=(a,b)=>source.slice(source.indexOf(a),source.indexOf(b,source.indexOf(a)));
const code=[between('function handoffMessage(', 'async function exportSection('),
  between('async function readCarCatalogue(', 'async function confirmCarReplacement('),
  between('function carJobValue(', 'async function switchCar(')].join('\n');
const id='d'.repeat(32),job='e'.repeat(32),car={car_id:3307,model_code:'TEST_CAR'};
const project={format:'kfps-livery-layout-v1',vehicle:car,vinyls:[],placements:[],
  vehicle_parts:{RearWing:7},authoring:{version:1,groups:[],locked:[],links:[]}};
const json=value=>JSON.parse(JSON.stringify(value));
function fixture({different=false,choice='discard',save=true,native=true,stale=false}={}){
  const nodes=new Map(),calls=[],opened=[],navigation=[];
  const location=new URL('http://127.0.0.1:4567/'+'a'.repeat(43)+'/#project='+id);
  const startup_session=location.href.split('#')[0];
  location.assign=url=>navigation.push(url);
  const context=vm.createContext({URL,File,TextEncoder,JSON,Number,Map,Set,setTimeout,clearTimeout,
    config:{host_project_handoff:true,car_switch:true,chrome_exposed:false,handoff_car_validation:true,
      vehicle:different?{car_id:1,model_code:'Other'}:car,sections:[{section:'Front'}]},
    window:{location,__kfpsStudioNativeDownloads:native,history:{state:null,replaceState(_s,_t,url){location.href=new URL(url,location).href;}}},
    completedHandoffs:new Set(),handoffWorking:false,disposed:false,sourceDocumentId:'one',busy:false,
    carWorking:false,carCommitting:false,carCancelRequested:false,carJob:null,carPicked:null,carCurrent:null,carCatalogue:[],navigationAuthorized:false,
    stop:{signal:{addEventListener(){},removeEventListener(){}}},
    $:key=>{if(!nodes.has(key))nodes.set(key,{value:'',textContent:'',hidden:false,classList:{toggle(){}},showModal(){},close(){}});return nodes.get(key);},
    t:x=>x,errorText:error=>error?.message||String(error),canPreview:()=>true,flushNumeric:()=>true,fingerprint:()=> 'revision-1',
    setBusy(value){context.busy=value;},interactionBusy:()=>context.busy,
    renderCars(){},refreshCars(){},carMessage(){},changed:()=>true,
    async confirmCarReplacement(){calls.push('confirm');return choice;},
    async downloadProject(){calls.push('save');return save;},takePackageStartupHandoff:()=>null,
    async fetch(url){calls.push(url);if(stale)context.sourceDocumentId='changed';return {ok:true,headers:{get:()=> 'application/json'},text:async()=>JSON.stringify({name:'Project',project,startup_session})};},
    validateProject(value,vehicle){assert.deepEqual(json(value.vehicle),json(vehicle));return value;},serializeProject:JSON.stringify,
    async openFile(file,options){assert.equal(options.isCurrent(),true);opened.push({value:JSON.parse(await file.text()),options});return true;},
    async api(route,body){calls.push(route);
      if(route==='cars')return {enabled:true,current:'1'.repeat(32),cars:[{car_id:1,model_code:'Other',name:'Other',id:'1'.repeat(32)},{...car,name:'Target',id:'2'.repeat(32)}]};
      if(route==='car-switch'){assert.deepEqual(json(body),{carId:'2'.repeat(32),projectId:id});return {id:job,status:'ready'};}
      if(route.endsWith('/commit'))return {id:job,status:'committed',url:location.origin+'/'+'b'.repeat(43)+'/'};
      throw Error(route);
    }
  });
  vm.runInContext(code,context);
  return {context,calls,opened,navigation,nodes,run:()=>context.importHostVinyl()};
}
for(const native of [true,false])test(`full project retains parts and authoring in ${native?'native':'Chrome'} same-car path`,async()=>{
  const h=fixture({native});await h.run();assert.equal(h.opened.length,1);assert.deepEqual(h.opened[0].value,project);
  assert.equal(h.context.window.location.hash,'');assert.equal(h.context.completedHandoffs.size,1);
});
for(const [choice,save] of [['cancel',true],['save',false]])test(`project ${choice}/${save} retains existing car and document`,async()=>{
  const h=fixture({different:true,choice,save});await h.run();assert.equal(h.opened.length,0);assert.equal(h.navigation.length,0);
  assert(h.calls.includes('confirm'));assert(!h.calls.includes('car-switch'));
});
test('save completes before project car preparation and opaque fragment survives',async()=>{
  const h=fixture({different:true,choice:'save'});await h.run();assert.equal(h.navigation.length,1);
  assert(h.calls.indexOf('save')<h.calls.indexOf('car-switch'));assert(h.navigation[0].endsWith('#project='+id));
});
test('Chrome never switches a shared project car',async()=>{
  const h=fixture({different:true,native:false});await h.run();assert.equal(h.opened.length,0);
  assert.equal(h.navigation.length,0);assert(!h.calls.includes('confirm'));
});
test('late linked handoff never replaces a different document',async()=>{
  const h=fixture({stale:true});await h.run();assert.equal(h.opened.length,0);assert.equal(h.context.completedHandoffs.size,0);
});
