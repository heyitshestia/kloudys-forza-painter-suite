const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const source=fs.readFileSync(path.join(__dirname,'../../../tools/livery-studio/src/web/livery-editor.mjs'),'utf8');
const between=(start,end)=>source.slice(source.indexOf(start),source.indexOf(end,source.indexOf(start)));
const code=[between('function initializeWorkspaceSession(', 'function refreshOutputSummary('),
  between('async function readCarCatalogue(', 'async function confirmCarReplacement('),
  between('function carJobValue(', 'async function switchCar('),
  between('function cancelCarSwitch(', 'async function exportSource(')].join('\n');
const carA={car_id:1,model_code:'A'},carB={car_id:2,model_code:'B'},jobId='e'.repeat(32);
const origin='http://127.0.0.1:5678',destination=origin+'/'+ 'b'.repeat(43)+'/';
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};

function fixture({holdPreparation=false}={}){
  const commit=deferred(),committing=deferred(),preparation=deferred(),preparing=deferred(),calls=[],navigation=[];
  const nodes=new Map();
  const context=vm.createContext({URL,Map,Set,JSON,Number,setTimeout,clearTimeout,
    config:{vehicle:carA,car_switch:true},sessionRestore:null,sessionLoading:false,
    sourceDocumentId:'document-1',commandRevision:0,numericEdited:new Set(),transform:null,drag:null,
    disposed:false,busy:false,saveWorking:false,carJob:null,carWorking:false,carCommitting:false,
    carCancelRequested:false,navigationAuthorized:false,carCatalogue:[],carCurrent:null,carPicked:null,
    projectStorage:{entry:()=>null},recovery:null,
    window:{__liveryLab:{ready:true},location:Object.assign(new URL(origin+'/'+ 'a'.repeat(43)+'/'),{assign:url=>navigation.push(url)})},
    document:{querySelector:()=>null,addEventListener(){}},stop:{signal:{addEventListener(){},removeEventListener(){}}},
    $:id=>{if(!nodes.has(id))nodes.set(id,{value:'',showModal(){},close(){}});return nodes.get(id);},
    changed:()=>false,refresh(){},renderCars(){},refreshCars(){},carMessage(){},message(){},
    errorText:error=>String(error?.message||error),t:value=>String(value),switchCar(){throw Error('Unexpected retry');},
    async api(route){
      calls.push(route);
      if(route==='cars')return {enabled:true,current:'1'.repeat(32),cars:[{...carA,id:'1'.repeat(32),name:'Car A'},{...carB,id:'2'.repeat(32),name:'Car B'}]};
      if(route==='car-switch'){preparing.resolve();if(holdPreparation)await preparation.promise;return {id:jobId,status:'ready'};}
      if(route===`car-switch/${jobId}/commit`){committing.resolve();return commit.promise;}
      if(route===`car-switch/${jobId}/cancel`)return {id:jobId,status:'cancelled'};
      throw Error('Unexpected route '+route);
    },
  });
  context.setBusy=value=>{context.busy=value;};
  context.interactionBusy=()=>context.busy||context.sessionLoading||context.sessionRestore?.state==='pending';
  vm.runInContext(code,context);context.initializeWorkspaceSession();
  return {context,api:context.window.kfpsWorkspaceSession,commit,committing,preparation,preparing,calls,navigation,
    start:()=>context.window.kfpsWorkspaceSession.restore({car:carB,dirty:false},'restore-1'),
    complete:(url=destination)=>commit.resolve({id:jobId,status:'committed',url})};
}

test('preparation cancellation remains accepted without commit or navigation',async()=>{
  const h=fixture({holdPreparation:true}),pending=h.start();await h.preparing.promise;
  assert.equal(h.api.cancelRestore('restore-1'),true);h.preparation.resolve();
  assert.equal((await pending).state,'cancelled');assert.equal(h.navigation.length,0);
  assert.equal(h.calls.some(route=>route.endsWith('/commit')),false);
  assert.equal(h.calls.filter(route=>route.endsWith('/cancel')).length,1);
});

test('cancellation during delayed commit is refused and committed destination is reconciled once',async()=>{
  const h=fixture(),pending=h.start();await h.committing.promise;
  assert.equal(h.context.carCommitting,true);
  assert.equal(h.api.cancelRestore('restore-1'),false);
  assert.equal(h.api.snapshot().restore.state,'pending');
  h.complete();assert.equal((await pending).state,'pending');
  assert.deepEqual(h.navigation,[destination]);assert.equal(h.context.carJob.status,'committed');
  assert.equal(h.api.cancelRestore('restore-1'),false);
  assert.equal((await h.start()).state,'pending');
  assert.equal(h.calls.filter(route=>route.endsWith('/commit')).length,1);
  assert.equal(h.calls.some(route=>route.endsWith('/cancel')),false);
});

test('late document guard cannot discard an already committed destination',async()=>{
  const h=fixture(),pending=h.start();await h.committing.promise;
  h.context.sourceDocumentId='document-2';h.complete();
  assert.equal((await pending).state,'pending');assert.deepEqual(h.navigation,[destination]);
  assert.equal(h.context.carJob.status,'committed');
});

test('rejected commit reports failure and never navigates',async()=>{
  const h=fixture(),pending=h.start();await h.committing.promise;
  h.commit.reject(Error('Commit rejected'));
  assert.equal((await pending).state,'failed');assert.equal(h.navigation.length,0);
});

test('commit receipt for another job is rejected without navigation',async()=>{
  const h=fixture(),pending=h.start();await h.committing.promise;
  h.commit.resolve({id:'f'.repeat(32),status:'committed',url:destination});
  assert.equal((await pending).state,'failed');assert.equal(h.navigation.length,0);
});

test('disposed owner cannot navigate from a late committed response',async()=>{
  const h=fixture(),pending=h.start();await h.committing.promise;
  h.context.disposed=true;h.complete();await pending;
  assert.equal(h.navigation.length,0);
});

for(const url of ['https://example.com/'+ 'b'.repeat(43)+'/',origin+'/bad/',origin+'/'+ 'a'.repeat(43)+'/']){
  test('committed response still rejects an unsafe destination: '+url,async()=>{
    const h=fixture(),pending=h.start();await h.committing.promise;h.complete(url);
    assert.equal((await pending).state,'failed');assert.equal(h.navigation.length,0);
    assert.equal(h.context.carJob.status,'committed');
  });
}
