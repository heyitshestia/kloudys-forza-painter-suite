const test = require('node:test');
const assert = require('node:assert/strict');
const {create} = require('../editor-diagnostics.js');

function fixture() {
  let now=0, next=0, frame=null, observer=null;
  const timeouts=new Map(), intervals=new Map(), listeners=new Map();
  const document={visibilityState:'visible',hasFocus:()=>true,addEventListener:(name,fn)=>listeners.set(name,fn)};
  const env={document,performance:{now:()=>now},crypto:globalThis.crypto,location:{hash:''},sessionStorage:{getItem:()=>null},
    addEventListener:()=>{},requestAnimationFrame:fn=>{frame=fn;return ++next;},cancelAnimationFrame:()=>{frame=null;},
    setTimeout:fn=>{const id=++next;timeouts.set(id,fn);return id;},clearTimeout:id=>timeouts.delete(id),
    setInterval:fn=>{const id=++next;intervals.set(id,fn);return id;},clearInterval:id=>intervals.delete(id),
    AbortController,fetch:async()=>({ok:true,json:async()=>({logging:{written:1,last_write:1}})}),
    PerformanceObserver:class {static supportedEntryTypes=['longtask'];constructor(fn){observer=fn;}observe(){}disconnect(){observer=null;}}};
  const api=create(env);
  return {api,env,timeouts,intervals,setTime:value=>{now=value;},frame:value=>{now=value;frame?.(value);},
    visibility:value=>{document.visibilityState=value;listeners.get('visibilitychange')();},
    task:(startTime,duration)=>observer({getEntries:()=>[{startTime,duration}]})};
}

test('hidden window time is not counted as a visible stall; missing heap stays unavailable',()=>{
  const f=fixture(); f.frame(10);f.frame(26);f.visibility('hidden');f.frame(5000);f.visibility('visible');f.frame(6000);f.frame(6016);
  const metrics=f.api.snapshot().metrics;
  assert.equal(metrics.totalGaps100,0);assert.equal(metrics.frameMax,16);assert.equal('heapBytes' in metrics,false);
  f.api.dispose();assert.equal(f.intervals.size,0);
});
test('delayed observer entries retain the action at the time of the stall',()=>{
  const f=fixture();f.setTime(100);f.api.action('rotate');f.setTime(390);f.api.finish();f.setTime(500);f.task(100,280);
  assert.equal(f.api.snapshot().events.at(-1).action,'rotate');
  assert.equal(f.api.snapshot().metrics.totalTasks,1);f.api.dispose();
});
test('pulse events and failed transport stay bounded; recovery never goes backwards',async()=>{
  const f=fixture();
  for(let i=0;i<1000;i++)f.api.pulse('zoom');
  assert.equal(f.timeouts.size,1);
  f.api.recovery(10,true,true);f.api.recovery(5,true,false);f.api.queued(11);
  assert.equal(f.api.snapshot().recovery.serverRevision,10);assert.equal(f.api.snapshot().recovery.browserRevision,10);
  f.env.fetch=async()=>{throw new Error('offline');};
  f.api.configure({headers:{'X-KFPS-Editor-Session':'test'}});
  await f.api.flush();
  for(let i=0;i<400;i++)f.api.record('edit');
  f.setTime(500);await f.api.flush();
  assert.equal(f.api.snapshot().events.length,48);assert.ok(f.api.snapshot().metrics.clientDrops>=350);
  assert.equal(f.api.snapshot().transportOk,false);
  f.env.fetch=async()=>({ok:true,json:async()=>({logging:{written:4}})});f.setTime(1000);await f.api.flush();
  assert.equal(f.api.snapshot().transportOk,true);assert.equal(f.api.snapshot().logging.written,4);
  f.api.dispose();assert.equal(f.timeouts.size,0);assert.equal(f.intervals.size,0);
});
