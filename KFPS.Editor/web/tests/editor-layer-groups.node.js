"use strict";
const assert=require("node:assert/strict");
const {create}=require("../editor-layer-groups.js");
(async()=>{
  let generation=0,commits=0,failRefresh=false,errors=0,answer;
  const objects=[{kloudy:{name:'A'}},{kloudy:{name:'B',locked:true}}];
  const groups=create({
    scene:{all:()=>objects,selected:()=>objects,groupIds:()=>[...new Set(objects.map(o=>o.kloudy.group_id).filter(Boolean))],
      members:ids=>objects.filter(o=>ids.includes(o.kloudy.group_id)),selectedMembers:()=>objects,
      attached:o=>objects.includes(o),groupName:o=>o.kloudy.group_name,typeLabel:()=>"Shape",expand:()=>{},lock:(o,v)=>{o.kloudy.locked=v;}},
    edits:{generation:()=>generation,commit:()=>commits++},
    view:{status:()=>{},render:()=>{},selection:()=>{},refresh:()=>{if(failRefresh)throw Error('display');},failed:()=>errors++},
    tr:(key,...args)=>key.replace(/\{(\d+)\}/g,(_,i)=>args[i]),requestName:()=>new Promise(resolve=>{answer=resolve;}),
  });
  assert.equal(groups.group(),true);assert.equal(commits,1);
  assert.equal(objects[0].kloudy.group_id,objects[1].kloudy.group_id);
  assert.equal(objects[1].kloudy.locked,true,'Grouping must preserve existing lock semantics');
  const stale=groups.renameGroup();generation++;answer('Stale');
  assert.equal(await stale,false);assert.equal(commits,1);
  const valid=groups.renameGroup();answer('Renamed');await valid;
  assert.equal(objects[1].kloudy.group_name,'Renamed');assert.equal(commits,2);
  failRefresh=true;groups.toggleVisibility();assert.equal(commits,3);assert.equal(errors,1);
  assert.equal(objects[0].visible,false);
  groups.ungroup();assert.equal(objects[0].kloudy.group_id,null);
  assert.equal(commits,4);
  console.log('editor-layer-groups: names, metadata, locks, stale rename and committed refresh failure passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
