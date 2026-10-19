'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const http = require('node:http');
const vm = require('node:vm');
const {setTimeout: sleep} = require('node:timers/promises');
const {create} = require('../activity-client.js');

function harness({ready=false, visible='visible', fails=false}={}) {
  let next=0, requests=0;
  const timers=new Map(), events={};
  const document={visibilityState:visible};
  const window={
    setTimeout(cb){timers.set(++next,cb);return next;}, clearTimeout(id){timers.delete(id);},
    requestAnimationFrame(cb){cb();}, addEventListener(name,cb){events[name]=cb;},
    focus(){throw new Error('Must not focus');}, open(){throw new Error('Must not open a window');},
  };
  const state={ready};
  const client=create({document,window,ready:()=>state.ready,request:async()=>{requests++;if(fails)throw new Error('offline');}});
  const advance=async()=>{const [id,cb]=timers.entries().next().value||[];assert(cb);timers.delete(id);await cb();};
  return {client,document,state,events,advance,timers,requests:()=>requests};
}

test('construct is inert, real ready and visible required, one signal only',async()=>{
  const h=harness();
  assert.equal(h.requests(),0);assert.equal(h.timers.size,0);
  h.client.start();await h.advance();assert.equal(h.requests(),0);
  h.state.ready=true;h.document.visibilityState='hidden';await h.advance();assert.equal(h.requests(),0);
  h.document.visibilityState='visible';await h.advance();assert.equal(h.requests(),1);
  assert.equal(h.timers.size,0);
});
test('closing before readiness sends nothing',async()=>{
  const h=harness();h.client.start();h.events.pagehide();
  assert.equal(h.timers.size,0);assert.equal(h.requests(),0);
});
test('failures have a bounded retry budget',async()=>{
  const h=harness({ready:true,fails:true});h.client.start();
  for(let i=0;i<3;i++)await h.advance();
  assert.equal(h.requests(),3);assert.equal(h.timers.size,0);
});
test('browser only contacts the local host and does not alter focus',()=>{
  const source=fs.readFileSync(require.resolve('../activity-client.js'),'utf8');
  for(const forbidden of ['https://','http://','webbrowser','window.focus','window.open'])assert(!source.includes(forbidden));
  assert(source.includes('document.visibilityState'));
  assert(source.includes('requestAnimationFrame'));
});

async function browserTransport(t, {status=200, body='{"ok":true}', stall=false}={}) {
  const source=fs.readFileSync(require.resolve('../activity-client.js'),'utf8');
  const timers=new Map(), events={}, signals=[], responses=[], controllers=[], requests=[];
  let readsStarted=0,readsCompleted=0;
  const server=http.createServer((request,response)=>{
    let incoming='';
    request.on('data',chunk=>incoming+=chunk);
    request.on('end',()=>{
      requests.push({path:request.url,body:incoming});
      response.writeHead(status,{'Content-Type':'application/json','Content-Length':Buffer.byteLength(body)});
      response.flushHeaders();
      if(!stall) {
        const id=setTimeout(()=>response.end(body),60);
        response.on('close',()=>clearTimeout(id));
      }
    });
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${server.address().port}/`;
  const document={visibilityState:'visible',currentScript:{dataset:{activityHost:'studio'}}};
  const window={
    __liveryLab:{ready:true},
    setTimeout(callback,delay){
      const id=setTimeout(()=>{timers.delete(id);callback();},delay);
      timers.set(id,delay);return id;
    },
    clearTimeout(id){clearTimeout(id);timers.delete(id);},
    requestAnimationFrame(callback){queueMicrotask(callback);},
    addEventListener(name,callback){events[name]=callback;},
  };
  class TrackedController extends AbortController {
    constructor(){super();controllers.push(this);}
  }
  const request=async(url,options)=>{
    signals.push(options.signal);
    const response=await fetch(new URL(url,base),options);
    const read=response.json.bind(response);
    response.json=async()=>{readsStarted++;const value=await read();readsCompleted++;return value;};
    responses.push(response);
    return response;
  };
  t.after(async()=>{
    events.pagehide?.();
    for(const id of timers.keys())clearTimeout(id);
    timers.clear();
    for(const controller of controllers)controller.abort();
    server.closeAllConnections();
    await new Promise(resolve=>server.close(resolve));
  });
  vm.runInNewContext(source,{window,document,location:{protocol:'http:',hash:''},
    fetch:request,AbortController:TrackedController,AbortSignal,URLSearchParams,
    setTimeout:window.setTimeout,clearTimeout:window.clearTimeout});
  const waitFor=async predicate=>{
    const end=Date.now()+6500;
    while(!predicate()) { assert(Date.now()<end,'Transport condition timed out');await sleep(10); }
  };
  await waitFor(()=>responses.length===1);
  return {timers,events,signals,responses,requests,waitFor,reads:()=>({readsStarted,readsCompleted})};
}

test('real browser request consumes 200 body and cannot abort after its completed deadline',async t=>{
  const h=await browserTransport(t);
  await sleep(4200);
  assert.deepEqual({bodyUsed:h.responses[0].bodyUsed,aborted:h.signals[0].aborted,
    activeTimers:h.timers.size,requests:h.requests.length},
    {bodyUsed:true,aborted:false,activeTimers:0,requests:1});
  assert.deepEqual(h.requests[0],{path:'/api/activity-ready',body:'{}'});
  assert.deepEqual(h.reads(),{readsStarted:1,readsCompleted:1});
});

test('real stalled response body aborts at the deadline and releases its timeout',async t=>{
  const h=await browserTransport(t,{stall:true});
  const started=Date.now();
  await h.waitFor(()=>h.signals[0].aborted);
  assert(Date.now()-started>=3500,'The actual four-second timeout must be exercised');
  await h.waitFor(()=>![...h.timers.values()].includes(4000));
  assert.equal(h.responses[0].bodyUsed,true);
  assert.deepEqual(h.reads(),{readsStarted:1,readsCompleted:0});
  h.events.pagehide();
  assert.equal(h.timers.size,0);
});

for(const [label,options] of [['HTTP failure',{status:503}],['malformed JSON',{body:'not json'}]]) {
  test(`real ${label} consumes the response and clears its deadline before retry`,async t=>{
    const h=await browserTransport(t,options);
    await h.waitFor(()=>h.responses[0].bodyUsed && [...h.timers.values()].includes(1500));
    assert(![...h.timers.values()].includes(4000));
    assert.equal(h.signals[0].aborted,false);
    h.events.pagehide();
    assert.equal(h.timers.size,0);
  });
}
