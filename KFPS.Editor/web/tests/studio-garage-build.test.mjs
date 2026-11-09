import test from 'node:test';
import assert from 'node:assert/strict';
import {BODY_PARTS,validateGarageBuild,resolveGarageBuild} from '../../../tools/livery-studio/src/web/garage-build.mjs';
import {componentCatalog,validateVehicleParts,componentMeshVisible,componentLabel} from '../../../tools/livery-studio/src/web/component-model.mjs';
import {validateProject,serializeProject} from '../../../tools/livery-studio/src/web/layout-model.mjs';
const fixture=()=>{
  const parts=Object.fromEntries(BODY_PARTS.map((part,index)=>[part,101+index]));
  const build={version:1,parts,fingerprint:'a'.repeat(64)};
  const options=Object.entries(parts).map(([part_type,id])=>({part_type,id,supported:true,baseline:true,stock:true}));
  options.push({part_type:'RearWing',id:999,supported:true,stock:false});
  return {build,options,catalog:componentCatalog(options)};
};
test('all body slots change atomically, metadata selects shared meshes correctly',()=>{
  const {build,catalog}=fixture();build.parts.RearWing=999;
  const parts=resolveGarageBuild(build,catalog),selection=validateVehicleParts(parts,catalog);
  assert.deepEqual(parts,build.parts);
  assert.equal(componentMeshVisible({kfps_part_type:'RearWing',kfps_part_option_ids:[106]},selection),false);
  assert.equal(componentMeshVisible({kfps_part_type:'RearWing',kfps_part_option_ids:[106,999]},selection),true);
  const vehicle={car_id:344,model_code:'NIS_FairladyZ_03'};
  const project=validateProject({format:'kfps-livery-layout-v1',vehicle,vinyls:[],placements:[],vehicle_parts:parts},vehicle,[]);
  assert.deepEqual(validateProject(JSON.parse(serializeProject(project)),vehicle,[]),project);
});
test('missing, unsupported and ambiguous selected options never fall back',()=>{
  for(const value of [null,-1,0,9999]) {
    const {build,catalog}=fixture();build.parts.ChassisStiffness=value;
    assert.throws(()=>resolveGarageBuild(build,catalog));
  }
  const {build,options}=fixture();
  assert.throws(()=>resolveGarageBuild(build,componentCatalog([...options,options[0]])));
  options[0].supported=false;
  assert.throws(()=>resolveGarageBuild(build,componentCatalog(options)));
});
test('absent source group is not a guessed removable part',()=>{
  const {build,options}=fixture(),catalog=componentCatalog(options.filter(row=>row.part_type!=='Hood'));
  assert.throws(()=>resolveGarageBuild(build,catalog));
  build.parts.Hood=null;
  assert.equal(Object.hasOwn(resolveGarageBuild(build,catalog),'Hood'),false);
});
test('fixed stock retains exact IDs, built-in meshes and saved projects only with current evidence',()=>{
  const {build,options}=fixture();
  const fixed={...options[0],empty:true,fixed_stock:true,source_kind:'database-fixed-stock',
    declared_instance_count:0,body_option_id:101,body_parent_id:500,car_body_id:-1,parent_upgrade_id:-1};
  const names={source:'installed fixture',same_build_verified:true,fixed_stock_options:[fixed]};
  const catalog=componentCatalog(options.slice(1),null,names);
  const parts=resolveGarageBuild(build,catalog),selection=validateVehicleParts(parts,catalog);
  assert.deepEqual(parts,build.parts);
  assert.equal(componentMeshVisible({kfps_part_type:'CarBody',kfps_stock_part:true,kfps_part_option_ids:[]},selection),true);
  assert(!componentLabel(catalog.groups.get('CarBody')[0]).includes('empty'));
  const vehicle={car_id:2738,model_code:'NIS_GTRLM_95'};
  const project=validateProject({format:'kfps-livery-layout-v1',vehicle,vinyls:[],placements:[],vehicle_parts:parts},vehicle,[]);
  assert.deepEqual(validateProject(JSON.parse(serializeProject(project)),vehicle,[]),project);
  assert.equal(componentCatalog(options,null,names).groups.get('CarBody').length,1);
  for(const change of [{same_build_verified:false},{source:''},{fixed_stock_options:[fixed,fixed]}])
    assert.throws(()=>resolveGarageBuild(build,componentCatalog(options.slice(1),null,{...names,...change})));
  for(const change of [{stock:false},{id:999},{body_option_id:999},{declared_instance_count:1},
    {supported:false},{parent_upgrade_id:500},{source_kind:'guessed'}])
    assert.throws(()=>resolveGarageBuild(build,componentCatalog(options.slice(1),null,{...names,fixed_stock_options:[{...fixed,...change}]})));
});
test('partial and private contracts rejected',()=>{
  const {build}=fixture();
  for(const patch of [{version:2},{parts:{}},{fingerprint:'bad'},{sourcePath:'private'}])assert.throws(()=>validateGarageBuild({...build,...patch}));
  for(const value of [true,'104',-2,2147483648,1.5])assert.throws(()=>validateGarageBuild({...build,parts:{...build.parts,Hood:value}}));
});
test('source-derived names retain IDs and ambiguous names are discarded',()=>{
  const {options}=fixture();
  const names={source:'fixture catalogue',reference_only:true,names:[{part_type:'RearWing',id:999,manufacturer:'Maker',product:'Carbon Wing'}]};
  let catalog=componentCatalog(options,null,names);
  assert.equal(componentLabel(catalog.groups.get('RearWing').find(row=>row.id===999)),'Maker / Carbon Wing (ID 999)');
  names.names.push({...names.names[0],manufacturer:'Conflicting maker'});
  catalog=componentCatalog(options,null,names);
  assert.equal(componentLabel(catalog.groups.get('RearWing').find(row=>row.id===999)),'Option (ID 999)');
});
test('explicit nonvisual upgrade retains its identity and common meshes, never a cage',()=>{
  const {build,options}=fixture();build.parts.ChassisStiffness=999;
  const row={part_type:'ChassisStiffness',id:999,car_body_id:500,parent_upgrade_id:500,supported:true,empty:true,
    declared_instance_count:0,source_kind:'database-nonvisual',requires_graphics:false};
  const names={source:'fixture reference',non_visual_options:[row]};
  const catalog=componentCatalog(options,null,names),selection=validateVehicleParts(resolveGarageBuild(build,catalog),catalog);
  assert.equal(selection.get('ChassisStiffness'),999);
  assert.equal(componentMeshVisible({kfps_part_type:'ChassisStiffness',kfps_part_option_ids:[102]},selection),false);
  assert.equal(componentMeshVisible({kfps_part_type:'ChassisStiffness',kfps_part_option_ids:[]},selection),true);
  for(const patch of [{requires_graphics:true},{declared_instance_count:1},{source_kind:'guessed'}])
    assert.throws(()=>resolveGarageBuild(build,componentCatalog(options,null,{...names,non_visual_options:[{...row,...patch}]})));
  assert.throws(()=>resolveGarageBuild(build,componentCatalog(options,null,{...names,non_visual_options:[row,row]})));
});
test('legacy body-only project resolves omitted slots but never overrides explicit incompatible parts',()=>{
  const options=[
    {part_type:'CarBody',id:10,stock:true,baseline:true,supported:true},
    {part_type:'CarBody',id:20,stock:false,supported:true},
    {part_type:'ChassisStiffness',id:101,car_body_id:1,stock:true,baseline:true,supported:true},
    {part_type:'ChassisStiffness',id:201,car_body_id:2,stock:true,supported:true},
  ];
  const catalog=componentCatalog(options,{source:'explicit join',parent_map:[
    {parent_upgrade_id:1,body_option_id:10},{parent_upgrade_id:2,body_option_id:20}]});
  const selection=validateVehicleParts({CarBody:20},catalog);
  assert.equal(selection.get('ChassisStiffness'),201);
  assert.throws(()=>validateVehicleParts({CarBody:20,ChassisStiffness:101},catalog),/incompatible/);
  assert.equal(validateVehicleParts(undefined,catalog).get('ChassisStiffness'),101);
});
