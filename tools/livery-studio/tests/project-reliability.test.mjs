import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRecoveryController} from '../src/web/recovery-ui.mjs';
import {createProjectSaveController} from '../src/web/project-storage-ui.mjs';
import {serializeProject,MAX_PROJECT_BYTES} from '../src/web/layout-model.mjs';

const vehicle={car_id:3307,model_code:'TEST_CAR'};
const project=()=>({format:'kfps-livery-layout-v1',vehicle,vinyls:[],placements:[]});
const id=n=>n.toString(16).padStart(32,'0');
const entry=n=>({id:id(n),document_id:id(500),kind:'auto',name:'Automatic recovery',created_at:'2026-11-11T00:00:00Z'});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};

test('combined managed and legacy recovery lists remain usable',async t=>{
  const entries=Array.from({length:192},(_,i)=>({...entry(i+1),...(i>=96?{source:'legacy'}:{})}));
  const controller=createRecoveryController({api:async()=>({version:1,entries}),getProject:project,loadProject:async()=>true});
  t.after(()=>controller.dispose());
  assert.equal((await controller.list()).length,192);
  assert.equal(controller.state().entries.length,192);
});

test('recovery list stays bounded and rejects duplicate identities',async t=>{
  let entries=Array.from({length:257},(_,i)=>entry(i+1));
  const controller=createRecoveryController({api:async()=>({version:1,entries}),getProject:project,loadProject:async()=>true});
  t.after(()=>controller.dispose());
  await assert.rejects(controller.list(),/Invalid recovery list/);
  entries=[entry(1),entry(1)];
  await assert.rejects(controller.list(),/Invalid recovery list/);
});

test('recovery restore guard rejects an edit begun during resource preparation',async t=>{
  let busy=false,loaded=false;
  const controller=createRecoveryController({api:async()=>({entry:entry(1),retained:entry(2),project:project()}),
    getProject:project,isBusy:()=>busy,loadProject:async(value,{isCurrent})=>{
      busy=true;
      if(!isCurrent())return false;
      loaded=true;return true;
    }});
  t.after(()=>controller.dispose());
  await assert.rejects(controller.restore(id(1)),/cancelled/);
  assert.equal(loaded,false);
});

test('recovery cannot apply a response for another entry',async t=>{
  let loaded=false;
  const controller=createRecoveryController({api:async()=>({entry:entry(9),retained:entry(2),project:project()}),
    getProject:project,loadProject:async()=>{loaded=true;return true;}});
  t.after(()=>controller.dispose());
  await assert.rejects(controller.restore(id(1)),/Invalid recovery response/);
  assert.equal(loaded,false);
});

test('cancelled or disposed restore preserves current document and pending recovery',async t=>{
  for(const dispose of [false,true]){
    const response=deferred();let loaded=false;
    const controller=createRecoveryController({api:()=>response.promise,getProject:project,
      loadProject:async()=>{loaded=true;return false;},debounceMs:10000});
    t.after(()=>controller.dispose());
    controller.changed();const pending=controller.restore(id(1));
    if(dispose)controller.dispose();
    response.resolve({entry:entry(1),retained:entry(2),project:project()});
    await assert.rejects(pending,/cancelled|changed/);
    assert.equal(loaded,!dispose);
    assert.equal(controller.state().pending,true);
  }
});

test('autosave keeps newer edits pending and does not retry a full store endlessly',async t=>{
  const response=deferred();let calls=0;
  const controller=createRecoveryController({api:()=>{calls++;return response.promise;},getProject:project,
    loadProject:async()=>true,debounceMs:100});
  t.after(()=>controller.dispose());
  controller.changed();const pending=controller.automatic();controller.changed();
  response.resolve({entry:entry(1)});await pending;
  assert.equal(controller.state().pending,true);
  controller.dispose();
  const failed=createRecoveryController({api:async()=>{calls++;throw Error('Recovery storage is full.');},
    getProject:project,loadProject:async()=>true,debounceMs:100});
  t.after(()=>failed.dispose());failed.changed();await failed.automatic();
  const before=calls;await new Promise(resolve=>setTimeout(resolve,140));
  assert.equal(calls,before);
  assert.equal(failed.state().pending,true);
  assert.match(failed.state().error,/full/);
});

test('managed save captures a frozen project and ignores late receipts after document switch',async()=>{
  const response=deferred();let current=project(),payload;
  const controller=createProjectSaveController({getProject:()=>current,api:async(route,value)=>{payload=value;return response.promise;}});
  const pending=controller.save('First');current.vehicle={car_id:4,model_code:'OTHER'};controller.adopt(null);
  response.resolve({entry:{id:id(1),revision:'a'.repeat(64),name:'First'}});
  const result=await pending;
  assert.equal(result.current,false);assert.equal(controller.entry(),null);
  assert.equal(payload.project.vehicle.car_id,3307);controller.dispose();
});

test('failed saves retain the prior receipt and allow retry',async()=>{
  let fail=true;
  const prior={id:id(1),revision:'a'.repeat(64),name:'First'};
  const controller=createProjectSaveController({getProject:project,api:async()=>{
    if(fail)throw Error('Storage unavailable');return {entry:{...prior,revision:'b'.repeat(64)}};
  }});
  controller.adopt(prior);await assert.rejects(controller.save('First'),/unavailable/);
  assert.deepEqual(controller.entry(),prior);fail=false;
  assert.equal((await controller.save('First')).entry.revision,'b'.repeat(64));controller.dispose();
});

test('project serializer falls back to exact compact JSON before rejecting the byte limit',()=>{
  const value=project(),compact=JSON.stringify(value);
  assert.equal(serializeProject(value,new TextEncoder().encode(compact).byteLength),compact);
  assert.throws(()=>serializeProject(value,compact.length-1),/32 MiB/);
});

test('maximum source-count project remains reopenable below the true byte limit',()=>{
  const shape={type:1048677,data:[0,0,1,1,0,0,0],color:[0,255,0,255],shape_name:'x'.repeat(400)};
  const value=project();
  value.vinyls=Array.from({length:16},(_,i)=>({id:`s${i}`,name:`Source ${i}`,shapes:Array(3000).fill(shape)}));
  assert(Buffer.byteLength(JSON.stringify(value))<MAX_PROJECT_BYTES);
  assert(Buffer.byteLength(JSON.stringify(value,null,2))>MAX_PROJECT_BYTES);
  const raw=serializeProject(value);
  assert(Buffer.byteLength(raw)<=MAX_PROJECT_BYTES);
  const reopened=JSON.parse(raw);assert.equal(reopened.vinyls.length,16);
  assert.equal(reopened.vinyls[15].shapes[2999].shape_name,shape.shape_name);
});
