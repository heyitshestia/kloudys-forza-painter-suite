"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const window={fabric:{version:'5.3.0'}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../editor-fabric-adapter.js'),'utf8'),{window});
const install=window.KfpsFabricAdapter.installInteractionOverlays;
const events=new Map(),calls=[];
let depth=0,active=false,error=null;
const context={save(){depth++;calls.push('save');},restore(){depth--;calls.push('restore');},transform(...matrix){calls.push(matrix);}};
const canvas={contextTop:context,contextContainer:{},viewportTransform:[2,0,0,2,30,40],
  on(name,fn){assert.ok(!events.has(name));events.set(name,fn);},
  clearContext(ctx){assert.equal(ctx,context);calls.push('clear');},
  renderTopLayer(ctx){assert.equal(ctx,context);calls.push('marquee');},
  drawControls(ctx){assert.equal(ctx,context);calls.push('controls');}};
const helper={canvas,visible:true,render(ctx){assert.equal(ctx,context);calls.push('guide');}};
const options={active:()=>active,helpers:()=>[helper,{canvas,visible:false,render(){throw Error('hidden');}},
  {canvas:{},render(){throw Error('detached');}}],onError(e){error=e;active=false;}};
assert.equal(install(canvas,options),true);assert.equal(install(canvas,options),true);assert.equal(events.size,1);
const paint=event=>events.get('after:render')(event);
paint();assert.deepEqual(calls,[]);
active=true;paint({ctx:{}});assert.deepEqual(calls,[]);
paint();assert.deepEqual(calls,['save',[2,0,0,2,30,40],'guide','restore','controls']);
assert.equal(canvas.contextTopDirty,true);assert.equal(depth,0);
calls.length=0;paint({ctx:canvas.contextContainer});
assert.deepEqual(calls,['clear','marquee','save',[2,0,0,2,30,40],'guide','restore','controls']);
calls.length=0;helper.render=()=>{throw Error('injected helper draw');};paint();
assert.equal(depth,0);assert.equal(error.message,'injected helper draw');assert.equal(calls.at(-1),'clear');
calls.length=0;paint();assert.deepEqual(calls,[]);
assert.equal(install({},options),false);
console.log('Interaction overlays: top/full frames, guide/control drawing, export isolation, lifecycle, repeat install and failure fallback passed');
