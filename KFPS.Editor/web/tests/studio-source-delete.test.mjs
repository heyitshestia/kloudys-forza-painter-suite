import assert from 'node:assert/strict';
import test from 'node:test';
import * as authoring from '../../../tools/livery-studio/src/web/authoring-model.mjs';
import {emptyProject, makePlacement, validateProject} from '../../../tools/livery-studio/src/web/layout-model.mjs';

const vehicle={car_id:2738,model_code:'nis_gtrlm_95'},sections=['Top','Right'];
function fixture(){
  const project=emptyProject(vehicle);
  project.vinyls=['a','b','unused'].map(id=>({id,name:id,shapes:[{type:1048677,data:[0,0,1,1,0,0,0],color:[255,0,0,255]}]}));
  project.placements=[makePlacement(project,'a','Top',sections,'p1'),makePlacement(project,'a','Right',sections,'p2'),
    makePlacement(project,'b','Top',sections,'p3'),makePlacement(project,'b','Right',sections,'p4')];
  project.authoring={version:1,groups:[{id:'g1',name:'Mixed',placements:['p1','p3']},{id:'g2',name:'Other',placements:['p2','p4']}],locked:[],links:[]};
  return project;
}
test('source deletion removes all uses and cleans groups without deleting other sources',()=>{
  const project=fixture(),before=structuredClone(project),next=authoring.removeVinylSource(project,'a');
  assert.deepEqual(project,before);
  assert.deepEqual(next.placements.map(p=>p.id),['p3','p4']);
  assert.deepEqual(next.vinyls.map(v=>v.id),['b','unused']);
  assert.equal(next.authoring,undefined);
  assert.doesNotThrow(()=>validateProject(next,vehicle,sections));
});
test('unused and last source can be removed',()=>{
  let project=fixture();
  project=authoring.removeVinylSource(project,'unused');
  assert.equal(project.placements.length,4);
  project=authoring.removeVinylSource(authoring.removeVinylSource(project,'a'),'b');
  assert.equal(project.placements.length,0);assert.equal(project.vinyls.length,0);
  assert.doesNotThrow(()=>validateProject(project,vehicle,sections));
});
test('one locked use blocks the whole operation',()=>{
  const project=fixture();project.authoring.locked=['p2'];const before=structuredClone(project);
  assert.throws(()=>authoring.removeVinylSource(project,'a'),/Unlock/);
  assert.deepEqual(project,before);
  assert.doesNotThrow(()=>authoring.removeVinylSource(project,'unused'));
});
test('missing or malformed source IDs never delete anything',()=>{
  const project=fixture(),before=structuredClone(project);
  for(const id of [null,{},'', 'absent'])assert.throws(()=>authoring.removeVinylSource(project,id));
  assert.deepEqual(project,before);
});
test('links touching deleted placements are removed, unrelated locks are retained',()=>{
  const project=fixture();project.placements[0].section='Left';project.authoring.groups=[];
  project.authoring.locked=['p4'];
  project.authoring.links=[{id:'link',a:'p1',b:'p2',sectionA:'Left',sectionB:'Right',mode:'readable-lettering',
    calibration:{kind:'user-aligned-pair-v1',aToB:[-1,0,0,1,0,0]}}];
  assert.doesNotThrow(()=>validateProject(project,vehicle,[...sections,'Left']));
  const next=authoring.removeVinylSource(project,'a');
  assert.deepEqual(next.authoring,{version:1,groups:[],locked:['p4'],links:[]});
  assert.doesNotThrow(()=>validateProject(next,vehicle,sections));
});
test('deletion handles the full placement limit across sections',()=>{
  const project=fixture();delete project.authoring;project.placements=[];
  project.placements=Array.from({length:200},(_,i)=>makePlacement(project,'a',sections[i%2],sections,'p'+i));
  const next=authoring.removeVinylSource(project,'a');
  assert.equal(next.placements.length,0);assert.equal(project.placements.length,200);
  assert.deepEqual(next.vinyls.map(v=>v.id),['b','unused']);
  assert.doesNotThrow(()=>validateProject(next,vehicle,sections));
});
