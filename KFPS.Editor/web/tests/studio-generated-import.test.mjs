import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createHistory,serializeProject,validateProject} from '../../../tools/livery-studio/src/web/layout-model.mjs';

const source=readFileSync(new URL('../../../tools/livery-studio/src/web/livery-editor.mjs',import.meta.url),'utf8');
const code=source.slice(source.indexOf('async function importFile('),source.indexOf('async function confirmReplace('));
const canonical={type:1048678,data:[0,0,2,1,330,0,0],color:[200,40,60,255],editor_group_id:'g'};
const input={shapes:[{type:16,data:[300,200,126,63,30],color:[200,40,60,255],editor_group_id:'g'}]};
function harness(fail='') {
  const calls=[],project={format:'kfps-livery-layout-v1',vehicle:{car_id:1,model_code:'test'},vinyls:[],placements:[]};
  const history=createHistory(10);let closes=0,current=true;
  const context=vm.createContext({JSON,Map,Set,structuredClone,MAX_VINYLS:16,MAX_PLACEMENTS:200,project,
    sources:new Map(),images:new Map(),dirtySections:new Set(),crypto:{randomUUID:()=> 'v'},selected:null,pickedSource:null,
    requirePreview(){if(fail==='closed')throw Error('closed');},
    api:async(name,body)=>{calls.push(name);assert.deepEqual(JSON.parse(JSON.stringify(body)),input);
      if(fail==='convert')throw Error('convert');if(fail==='cancel')current=false;return {shapes:[structuredClone(canonical)]};},
    raster:async shapes=>{calls.push('render');assert.deepEqual(JSON.parse(JSON.stringify(shapes)),[canonical]);
      if(fail==='render')throw Error('render');return {close(){closes++;}};},
    snapshot:()=>structuredClone(project),serializeProject,
    createPlacement:()=>({id:'p',vinylId:'v',section:'Left',x:0,y:0,scaleX:1,scaleY:1,rotation:0,opacity:1,visible:true}),
    schedule(){},commit(before){history.push(before,structuredClone(project));},message(){},diagnostics:{emit(){}},
    projectCounts:()=>({}),config:{sections:[{section:'Left'}]},
  });
  vm.runInContext(code,context);
  return {context,calls,history,project,get closes(){return closes;},current:()=>current};
}
test('actual file-import function retains converted shapes through project save/reopen and undo/redo',async()=>{
  const h=harness(),before=structuredClone(input);
  await h.context.importFile({name:'generated.json',size:200,text:async()=>JSON.stringify(input)});
  assert.deepEqual(h.calls,['import-vinyl','render']);
  assert.deepEqual(h.project.vinyls[0].shapes,[canonical]);assert.deepEqual(input,before);
  const reopened=validateProject(JSON.parse(serializeProject(h.project)),h.project.vehicle,['Left']);
  assert.deepEqual(reopened.vinyls[0].shapes,[canonical]);
  assert.equal(h.history.undo(h.project).vinyls.length,0);
  assert.equal(h.history.redo({}).vinyls.length,1);
  assert.equal(h.closes,0);
});
for(const failure of ['convert','render','closed','cancel'])test(`failed/cancelled import leaves the document unchanged: ${failure}`,async()=>{
  const h=harness(failure),before=serializeProject(h.project);
  const promise=h.context.importFile({name:'generated.json',size:200,text:async()=>JSON.stringify(input)},{isCurrent:h.current});
  if(failure==='cancel')await promise;else await assert.rejects(promise,new RegExp(failure));
  assert.equal(serializeProject(h.project),before);assert.equal(h.context.images.size,0);assert.equal(h.context.sources.size,0);
  if(failure==='cancel')assert.deepEqual(h.calls,['import-vinyl']);
});
