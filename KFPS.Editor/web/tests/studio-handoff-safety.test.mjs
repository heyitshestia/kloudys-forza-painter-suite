import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {validateProject,serializeProject} from '../../../tools/livery-studio/src/web/layout-model.mjs';
import {validateGarageBuild} from '../../../tools/livery-studio/src/web/garage-build.mjs';

const source=fs.readFileSync(new URL('../../../tools/livery-studio/src/web/livery-editor.mjs',import.meta.url),'utf8');
const body=source.slice(source.indexOf('async function openPackageArtwork('),source.indexOf('async function importHostVinyl('));
const run=new Function('context',`const {config,window,validateGarageBuild,garageVehicleParts,validateProject,serializeProject,confirmCarReplacement,downloadProject,handoffMessage,restoreSessionCar,openFile}=context;${body};return openPackageArtwork;`);
const base='http://127.0.0.1:1234/'+'a'.repeat(43)+'/',id='b'.repeat(32);
const old={car_id:1,model_code:'OLD'},target={car_id:344,model_code:'NIS_FairladyZ_03'};
function fixture(){
  const calls=[];
  const context={config:{vehicle:old,sections:[{section:'Top'}],host_garage_build:true,car_switch:true,chrome_exposed:false,handoff_car_validation:true},
    window:{__kfpsStudioNativeDownloads:true,location:{href:base+'#layout='+id,hash:'#layout='+id}},
    validateProject,serializeProject,validateGarageBuild,garageVehicleParts:()=>{calls.push('parts');throw Error('Unavailable Garage component');},
    confirmCarReplacement:async()=>{calls.push('confirm');return 'discard';},downloadProject:async()=>true,handoffMessage:()=>{},
    restoreSessionCar:async(...args)=>{calls.push(['switch',...args]);return 'pending';},openFile:()=>{calls.push('open');return true;}};
  const value={name:'fixture',startup_session:base,layout:{format:'kfps-livery-layout-v1',vehicle:target,vinyls:[],placements:[]}};
  return {context,value,calls,open:()=>run(context)(value,()=>true)};
}
test('loaded editor refuses shared, stale and unsupported cross-car handoffs before replacement',async()=>{
  for(const change of ['shared','unknown','expired','old-backend','chrome']){
    const f=fixture();
    if(change==='shared')f.context.config.chrome_exposed=true;
    if(change==='unknown')delete f.context.config.chrome_exposed;
    if(change==='expired')delete f.value.startup_session;
    if(change==='old-backend')delete f.context.config.handoff_car_validation;
    if(change==='chrome')f.context.window.__kfpsStudioNativeDownloads=false;
    await assert.rejects(f.open());assert.deepEqual(f.calls,[],change);
  }
});
test('loaded editor binds cross-car preparation to the exact incoming handoff',async()=>{
  const f=fixture();assert.equal(await f.open(),false);
  assert.equal(f.calls[0],'confirm');assert.equal(f.calls[1][0],'switch');
  assert.deepEqual(f.calls[1][1],target);assert.equal(f.calls[1][3],id);
  assert(!f.calls.includes('open'));
});
test('same-car invalid body is rejected before save/discard or document replacement',async()=>{
  const f=fixture();f.context.config.vehicle=target;
  f.value.layout.garage_build={version:1,fingerprint:'c'.repeat(64),parts:Object.fromEntries(
    ['CarBody','ChassisStiffness','FrontBumper','Hood','RearBumper','RearWing','SideSkirts'].map(p=>[p,9999]))};
  await assert.rejects(f.open(),/Unavailable Garage component/);assert.deepEqual(f.calls,['parts']);
});
