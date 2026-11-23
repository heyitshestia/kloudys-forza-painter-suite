import test from 'node:test';
import assert from 'node:assert/strict';
import {componentCatalog, initialComponentSelection, selectComponent,
  validateVehicleParts, componentCompatibility, componentMeshVisible} from '../src/web/component-model.mjs';
import {resolveGarageBuild, BODY_PARTS} from '../src/web/garage-build.mjs';

const row=(part_type,id,extra={})=>({part_type,id,supported:true,stock:false,car_body_id:-1,...extra});
const fit=parent_map=>({source:'synthetic exact joins',parent_map});
const join=(parent_upgrade_id,body_option_id)=>({parent_upgrade_id,body_option_id});
const build=parts=>({version:1,fingerprint:'a'.repeat(64),parts:Object.fromEntries(BODY_PARTS.map(k=>[k,parts[k]??null]))});

test('duplicate IDs cannot be selected manually, restored or applied by Garage',()=>{
  for(const duplicate of [row('Hood',7),row('Hood',7,{supported:false})]) {
    for(const values of [[row('Hood',7,{stock:true}),duplicate],[duplicate,row('Hood',7,{stock:true})]]) {
      const catalog=componentCatalog(values),selection=initialComponentSelection(catalog);
      assert.equal(selection.get('Hood'),null);
      assert.equal(selectComponent(catalog,selection,'Hood',7),false);
      assert.throws(()=>validateVehicleParts({Hood:7},catalog),/component|ambiguous/i);
      assert.throws(()=>resolveGarageBuild(build({Hood:7}),catalog),/component|ambiguous/i);
    }
  }
});

test('a conflicting parent is not the same as an unknown parent',()=>{
  const values=[row('CarBody',1,{stock:true}),row('CarBody',2),row('Hood',7,{car_body_id:10})];
  const conflict=componentCatalog(values,fit([join(10,1),join(10,2)]));
  const selection=initialComponentSelection(conflict),hood=conflict.groups.get('Hood')[0];
  assert.equal(componentCompatibility(hood,conflict,selection),false);
  assert.equal(selectComponent(conflict,selection,'Hood',7),false);
  assert.throws(()=>validateVehicleParts({CarBody:1,Hood:7},conflict),/component|ambiguous/i);
  assert.throws(()=>resolveGarageBuild(build({CarBody:1,Hood:7}),conflict),/component|ambiguous/i);
  const unknown=componentCatalog(values);
  assert.equal(componentCompatibility(unknown.groups.get('Hood')[0],unknown,new Map([['CarBody',1]])),null);
  assert.doesNotThrow(()=>validateVehicleParts({CarBody:1,Hood:7},unknown));
});

test('conflict with an undeclared body must not disappear during catalogue filtering',()=>{
  const catalog=componentCatalog([row('CarBody',1,{stock:true}),row('Hood',7,{car_body_id:10})],
    fit([join(10,1),join(10,999)]));
  assert.throws(()=>resolveGarageBuild(build({CarBody:1,Hood:7}),catalog),/component|ambiguous/i);
});

test('unknown mapped body and explicitly unresolved current evidence are blocked, not guessed',()=>{
  const values=[row('CarBody',1,{stock:true}),row('Hood',7,{stock:true,car_body_id:10})];
  for(const evidence of [fit([join(10,999)]),{...fit([]),unresolved_parent_ids:[10]}]) {
    const catalog=componentCatalog(values,evidence);
    assert.throws(()=>resolveGarageBuild(build({CarBody:1,Hood:7}),catalog),/component/i);
    assert.throws(()=>validateVehicleParts({CarBody:1,Hood:7},catalog),/component/i);
  }
});

test('ambiguous defaults stay empty instead of picking the first aftermarket ID',()=>{
  for(const flags of [{},{stock:true},{baseline:true}]) {
    const catalog=componentCatalog([row('CarBody',1,{stock:true}),
      row('Hood',7,{car_body_id:10,...flags}),row('Hood',8,{car_body_id:10,...flags})],fit([join(10,1)]));
    assert.equal(initialComponentSelection(catalog).get('Hood'),null);
    assert.equal(componentMeshVisible({kfps_part_type:'Hood',kfps_part_option_ids:[7]},initialComponentSelection(catalog)),false);
    assert.equal(componentMeshVisible({kfps_part_type:'CarBody',kfps_part_option_ids:[]},initialComponentSelection(catalog)),true);
  }
});

test('a unique compatible stock option remains selected and explicit choices remain exact',()=>{
  const catalog=componentCatalog([row('CarBody',1,{stock:true}),row('CarBody',2),
    row('Hood',7,{car_body_id:10,stock:true}),row('Hood',8,{car_body_id:20,stock:true}),
    row('Hood',9,{car_body_id:20})],fit([join(10,1),join(20,2)]));
  assert.equal(initialComponentSelection(catalog).get('Hood'),7);
  assert.equal(validateVehicleParts({CarBody:2},catalog).get('Hood'),8);
  assert.equal(validateVehicleParts({CarBody:2,Hood:9},catalog).get('Hood'),9);
  assert.throws(()=>validateVehicleParts({CarBody:2,Hood:7},catalog),/incompatible/);
});

test('malformed relationship evidence never becomes an unknown-compatible fallback',()=>{
  const values=[row('CarBody',1,{stock:true}),row('Hood',7,{car_body_id:10})];
  for(const change of [{unresolved_parent_ids:{}},{unresolved_parent_ids:[[10]]},
    {parent_map:[join(true,1)]},{parent_map:{}}]) {
    const catalog=componentCatalog(values,{...fit([]),...change});
    assert.throws(()=>validateVehicleParts({CarBody:1,Hood:7},catalog),/component|compatibility/i);
    assert.throws(()=>resolveGarageBuild(build({CarBody:1,Hood:7}),catalog),/component|compatibility/i);
  }
});
