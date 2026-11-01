import assert from 'node:assert/strict';
import {createSourceEditMonitor} from '../../tools/livery-studio/src/web/source-edit-monitor.mjs';
import {readFile} from 'node:fs/promises';
import en from '../../tools/livery-studio/src/web/locales/en.mjs';
import ko from '../../tools/livery-studio/src/web/locales/ko.mjs';
import ja from '../../tools/livery-studio/src/web/locales/ja.mjs';

const messages=JSON.parse(await readFile(new URL('../../tools/livery-studio/src/web/locales/messages.json',import.meta.url),'utf8'));
for(const key of ['2D editor opened. Use Return to Studio when ready.','Automatic checks paused. Use Check changes to retry.']){
  assert.equal(en[key],key);
  assert.equal(ko[key],messages[key][0]);
  assert.equal(ja[key],messages[key][1]);
}

let tasks=new Map(),sequence=0,calls=0,results=[],resolve;
const job={id:'a',status:'editing'};
const monitor=createSourceEditMonitor({
  read:async()=>{calls++;return await new Promise(done=>resolve=done);},
  update:(target,value)=>{assert.equal(target,job);results.push(value);target.status=value.status;},
  schedule:(fn,ms)=>{tasks.set(++sequence,{fn,ms});return sequence;},cancel:id=>tasks.delete(id),
});
monitor.start(job);
let pending=monitor.check();
await monitor.check();
assert.equal(calls,1,'Only one request can be in flight');
resolve({status:'editing'});await pending;
assert.equal(tasks.size,1);
pending=monitor.check();monitor.stop();resolve({status:'ready'});await pending;
assert.equal(results.length,1,'Late results cannot update cancelled links');
assert.equal(tasks.size,0);
monitor.start(job);pending=monitor.check();resolve({status:'ready'});await pending;
assert.equal(tasks.size,0,'Ready artwork stops polling');
assert.equal(results.length,2);
let failures=0,errors=0;
const retry=createSourceEditMonitor({read:async()=>{failures++;throw Error('offline');},update:()=>assert.fail(),onError:()=>errors++,
  schedule:(fn,ms)=>{tasks.set(++sequence,{fn,ms});return sequence;},cancel:id=>tasks.delete(id)});
retry.start({id:'b'});
for(let i=0;i<5;i++)await retry.check();
assert.equal(failures,5);assert.equal(errors,1);assert.equal(tasks.size,0,'Failures are bounded');
await retry.check();assert.equal(failures,6,'Manual retry remains available');
retry.stop();
const requests=[],updates=[];
const switched=createSourceEditMonitor({read:target=>new Promise(done=>requests.push({target,done})),
  update:(target,value)=>{updates.push(target.id);target.status=value.status;},
  schedule:(fn,ms)=>{tasks.set(++sequence,{fn,ms});return sequence;},cancel:id=>tasks.delete(id)});
const oldJob={id:'old',status:'editing'},newJob={id:'new',status:'editing'};
switched.start(oldJob);const oldRequest=switched.check();
switched.start(newJob);const newRequest=switched.check();
requests[0].done({status:'ready'});await oldRequest;
await switched.check();assert.equal(requests.length,2,'Old reply cannot clear the new pending request');
requests[1].done({status:'stale'});await newRequest;
assert.deepEqual(updates,['new']);assert.equal(tasks.size,0,'Stale jobs stop polling');
switched.stop();
console.log('source-edit monitor: coalescing, stale replies, readiness, cancellation and bounded failures passed');
