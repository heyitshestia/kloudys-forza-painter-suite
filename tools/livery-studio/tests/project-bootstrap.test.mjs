import {test} from 'node:test';
import assert from 'node:assert/strict';
import {preparePackageStartup,takePackageStartupHandoff} from '../src/web/studio-bootstrap.mjs';
const car={car_id:3307,model_code:'TEST_CAR'},id='a'.repeat(32),carId='b'.repeat(32),job='c'.repeat(32);
const base='http://127.0.0.1:1234/'+'d'.repeat(43)+'/',next='http://127.0.0.1:1234/'+'e'.repeat(43)+'/';
function fixture({different=false,native=true}={}) {
  const events=new EventTarget(),calls=[],navigation=[];
  const window={location:{href:base+'#project='+id,hash:'#project='+id,assign:url=>navigation.push(url)},
    __kfpsStudioNativeDownloads:native,addEventListener:events.addEventListener.bind(events),removeEventListener:events.removeEventListener.bind(events)};
  const project={format:'kfps-livery-layout-v1',vehicle:car,vinyls:[],placements:[],vehicle_parts:{RearWing:7}};
  const request=async(route,body)=>{
    calls.push([route,body]);
    if(route==='editor-config')return {vehicle:different?{car_id:1,model_code:'OTHER'}:car,host_project_handoff:true,chrome_exposed:false,car_switch:true,handoff_car_validation:true};
    if(route==='host-project/'+id)return {name:'Project',project,startup_session:base};
    if(route==='cars')return {cars:[{id:carId,...car}],current:null};
    if(route==='car-switch'){assert.deepEqual(body,{carId,projectId:id});return {id:job,status:'ready'};}
    if(route.endsWith('/commit'))return {id:job,status:'committed',url:next};
    throw Error(route);
  };
  return {window,request,calls,navigation,project};
}
test('project startup freezes body for one exact-car adoption',async()=>{
  const h=fixture();assert.equal(await preparePackageStartup(h),true);
  assert.deepEqual(h.calls.map(x=>x[0]),['editor-config','host-project/'+id]);
  assert.deepEqual(takePackageStartupHandoff(id,h.window,'project').project,h.project);
  assert.equal(takePackageStartupHandoff(id,h.window,'project'),null);
});
test('native project startup uses guarded car preparation',async()=>{
  const h=fixture({different:true});assert.equal(await preparePackageStartup(h),false);
  assert.deepEqual(h.navigation,[next+'#project='+id]);
});
test('Chrome startup cannot switch project car',async()=>{
  const h=fixture({different:true,native:false});await assert.rejects(preparePackageStartup(h),/Chrome/);
  assert(!h.calls.some(x=>x[0]==='car-switch'));
});
