const assert = require('node:assert/strict');
const {test} = require('node:test');
const {pathToFileURL} = require('node:url');
const path = require('node:path');
const fs = require('node:fs');
const web = path.resolve(__dirname, '../../../tools/livery-studio/src/web');
const moduleReady = import(pathToFileURL(path.join(web, 'studio-bootstrap.mjs')).href);
const target = {car_id:3307, model_code:'PACKAGE_CAR'};
const old = {car_id:99, model_code:'DEFAULT'};
const hash = '#layout=' + 'a'.repeat(32);
const jobId = 'b'.repeat(32), carId = 'c'.repeat(32);
const base = 'http://127.0.0.1:1234/' + 'd'.repeat(43) + '/';
const next = 'http://127.0.0.1:1234/' + 'e'.repeat(43) + '/';

function fixture({native=true, vehicle=old, hook}={}) {
  const events = new EventTarget(), calls=[], navigations=[];
  const window = {location:{href:base+hash, origin:new URL(base).origin, pathname:new URL(base).pathname,
    hash, assign:url=>navigations.push(url)}, __kfpsStudioNativeDownloads:native,
    addEventListener:events.addEventListener.bind(events), removeEventListener:events.removeEventListener.bind(events)};
  const request = async (route, body) => {
    calls.push([route,body]);
    const overridden = await hook?.(route,body,window);
    if(overridden !== undefined)return overridden;
    if(route==='editor-config')return {vehicle, host_layout_handoff:true, car_switch:true, chrome_exposed:false,handoff_car_validation:true};
    if(route.startsWith('host-layout/'))return {name:'Fixture',startup_session:base,layout:{format:'kfps-livery-layout-v1',vehicle:target,vinyls:[],placements:[]}};
    if(route==='cars')return {cars:[{id:carId,...target}], current:null};
    if(route==='car-switch')return {id:jobId,status:'ready'};
    if(route.endsWith('/cancel'))return {id:jobId,status:'cancelled'};
    if(route.endsWith('/commit'))return {id:jobId,status:'committed',url:next};
    throw Error('Unexpected request: '+route);
  };
  return {window,request,wait:async()=>{},events,calls,navigations};
}

test('ordinary startup does not issue package requests',async()=>{
  const f=fixture();f.window.location.hash='';
  assert.equal(await (await moduleReady).preparePackageStartup(f),true);
  assert.deepEqual(f.calls,[]);
});

test('cross-car startup requires server validation and sends the exact layout grant',async()=>{
  const f=fixture();await (await moduleReady).preparePackageStartup(f);
  assert.deepEqual(f.calls.find(x=>x[0]==='car-switch')[1],{carId,layoutId:'a'.repeat(32)});
  const oldServer=fixture({hook:route=>route==='editor-config'?{vehicle:old,host_layout_handoff:true,car_switch:true,chrome_exposed:false}:undefined});
  await assert.rejects((await moduleReady).preparePackageStartup(oldServer),/restart Studio/);
  assert(!oldServer.calls.some(x=>x[0]==='car-switch'));
});
test('cold exact-car startup does not prepare a second car',async()=>{
  const f=fixture({vehicle:target});
  assert.equal(await (await moduleReady).preparePackageStartup(f),true);
  assert.deepEqual(f.calls.map(x=>x[0]),['editor-config','host-layout/'+'a'.repeat(32)]);
});
test('validated startup handoff is reusable once without another fetch',async()=>{
  const f=fixture({vehicle:target}), module=await moduleReady;
  await module.preparePackageStartup(f);
  const value=module.takePackageStartupHandoff('a'.repeat(32),f.window);
  assert.equal(value.name,'Fixture');
  assert.equal(module.takePackageStartupHandoff('a'.repeat(32),f.window),null);
  assert.equal(f.calls.filter(x=>x[0].startsWith('host-layout/')).length,1);
});
test('startup handoff cache rejects changed hash, token and owner',async()=>{
  const module=await moduleReady;
  for(const change of ['hash','token','owner','pagehide','clear']){
    const f=fixture({vehicle:target});
    await module.preparePackageStartup(f);
    let owner=f.window;
    if(change==='hash'){f.window.location.hash='#layout='+'f'.repeat(32);f.events.dispatchEvent(new Event('hashchange'));}
    if(change==='token')f.window.location.href=next+hash;
    if(change==='owner')owner=fixture().window;
    if(change==='pagehide')f.events.dispatchEvent(new Event('pagehide'));
    if(change==='clear')module.clearPackageStartupHandoff();
    assert.equal(module.takePackageStartupHandoff('a'.repeat(32),owner),null,change);
    assert.equal(module.takePackageStartupHandoff('a'.repeat(32),f.window),null,change);
  }
});
test('unused startup handoff expires and releases its timer',async()=>{
  const module=await moduleReady,f=fixture({vehicle:target});
  const originalSet=global.setTimeout,originalClear=global.clearTimeout;let expire,cleared=0;
  global.setTimeout=(callback,delay)=>{assert.equal(delay,30000);expire=callback;return {unref(){}};};
  global.clearTimeout=()=>{cleared++;};
  try{
    await module.preparePackageStartup(f);expire();
    assert.equal(module.takePackageStartupHandoff('a'.repeat(32),f.window),null);
    assert.equal(cleared,1);
  }finally{module.clearPackageStartupHandoff();global.setTimeout=originalSet;global.clearTimeout=originalClear;}
});
test('native fresh-document mismatch commits before permitting any scene import',async()=>{
  const f=fixture();
  assert.equal(await (await moduleReady).preparePackageStartup(f),false);
  assert.equal(f.calls.find(x=>x[0]==='car-switch')[1].carId,carId);
  assert.deepEqual(f.navigations,[next+hash]);
});
test('Chrome mismatch cannot prepare or commit',async()=>{
  const f=fixture({native:false});
  await assert.rejects((await moduleReady).preparePackageStartup(f),/Chrome/);
  assert.equal(f.calls.some(x=>x[0].startsWith('car-switch')),false);
});
test('native shared or obsolete-session handoff cannot auto-switch',async()=>{
  for(const startup_session of [undefined,next]){
    const f=fixture({hook:route=>route.startsWith('host-layout/')?{name:'Fixture',startup_session,
      layout:{format:'kfps-livery-layout-v1',vehicle:target,vinyls:[],placements:[]}}:undefined});
    await assert.rejects((await moduleReady).preparePackageStartup(f),/another open page/);
    assert.equal(f.calls.some(x=>x[0].startsWith('car-switch')),false);
  }
});
test('native lease and valid handoff cannot switch a Chrome-exposed or unknown backend',async()=>{
  for(const chrome_exposed of [true,undefined]){
    const f=fixture({hook:route=>route==='editor-config'?{
      vehicle:old,host_layout_handoff:true,car_switch:true,chrome_exposed}:undefined});
    await assert.rejects((await moduleReady).preparePackageStartup(f),/another open page/);
    assert.equal(f.calls.some(x=>x[0].startsWith('car-switch')),false);
    assert.deepEqual(f.navigations,[]);
  }
});
test('missing and ambiguous exact targets fail closed',async()=>{
  for(const cars of [[],[{id:carId,...target},{id:'f'.repeat(32),...target}]]){
    const f=fixture({hook:route=>route==='cars'?{cars,current:null}:undefined});
    await assert.rejects((await moduleReady).preparePackageStartup(f),/exact|ambiguous/);
    assert.equal(f.calls.some(x=>x[0]==='car-switch'),false);
  }
});
test('malformed layout is rejected before starting work',async()=>{
  const f=fixture({hook:route=>route.startsWith('host-layout/')?{layout:{vehicle:target}}:undefined});
  await assert.rejects((await moduleReady).preparePackageStartup(f));
  assert.equal(f.calls.some(x=>x[0]==='car-switch'),false);
});
test('superseded preflight does not prepare stale target',async()=>{
  const f=fixture({hook:(route,body,window)=>{if(route==='cars')window.location.hash='';}});
  assert.equal(await (await moduleReady).preparePackageStartup(f),true);
  assert.equal(f.calls.some(x=>x[0]==='car-switch'),false);
});
test('superseded start receipt is cancelled before returning to startup',async()=>{
  const f=fixture({hook:(route,body,window)=>{if(route==='car-switch')window.location.hash='';}});
  assert.equal(await (await moduleReady).preparePackageStartup(f),true);
  assert.equal(f.calls.filter(x=>x[0].endsWith('/cancel')).length,1);
  assert.equal(f.calls.some(x=>x[0].endsWith('/commit')),false);
});
test('cancelling obsolete preparation is polled to completion before continuing',async()=>{
  let waits=0;
  const f=fixture({hook:(route,body,window)=>{
    if(route==='car-switch'){window.location.hash='';return {id:jobId,status:'preparing'};}
    if(route.endsWith('/cancel'))return {id:jobId,status:'cancelling'};
    if(route===`car-switch/${jobId}`)return {id:jobId,status:'cancelled'};
  }});
  f.wait=async()=>{if(++waits>3)throw Error('Obsolete cancellation was never polled');};
  assert.equal(await (await moduleReady).preparePackageStartup(f),true);
  assert.equal(f.calls.filter(x=>x[0].endsWith('/cancel')).length,1);
  assert.equal(f.calls.filter(x=>x[0]===`car-switch/${jobId}`).length,1);
});
test('pagehide while polling cannot commit a ready reply',async()=>{
  const f=fixture({hook:route=>{
    if(route==='car-switch')return {id:jobId,status:'preparing'};
    if(route===`car-switch/${jobId}`){f.events.dispatchEvent(new Event('pagehide'));return {id:jobId,status:'ready'};}
  }});
  assert.equal(await (await moduleReady).preparePackageStartup(f),false);
  assert.equal(f.calls.filter(x=>x[0].endsWith('/cancel')).length,1);
  assert.equal(f.calls.some(x=>x[0].endsWith('/commit')),false);
});
test('late supersession reconciles rotated token with newest opaque fragment',async()=>{
  const latest='#layout='+'f'.repeat(32);
  const f=fixture({hook:(route,body,window)=>{if(route.endsWith('/commit'))window.location.hash=latest;}});
  assert.equal(await (await moduleReady).preparePackageStartup(f),false);
  assert.deepEqual(f.navigations,[next+latest]);
});
test('lost commit response never retries, cancels or imports an obsolete scene',async()=>{
  const f=fixture({hook:route=>{if(route.endsWith('/commit'))throw Error('Network lost');}});
  await assert.rejects((await moduleReady).preparePackageStartup(f),/could not be confirmed.*Reopen Studio/);
  assert.equal(f.calls.filter(x=>x[0].endsWith('/commit')).length,1);
  assert.equal(f.calls.some(x=>x[0].endsWith('/cancel')),false);
  assert.deepEqual(f.navigations,[]);
});
test('fetch deadline rejects late response even after hash changes',async()=>{
  const original=global.fetch,f=fixture();let resolve,signal,calls=0;
  global.fetch=async(url,options)=>{calls++;signal=options.signal;return new Promise(done=>{resolve=done;});};
  try{
    await assert.rejects((await moduleReady).preparePackageStartup({window:f.window,requestTimeoutMs:5}),/timed out/);
    assert.equal(signal.aborted,true);
    f.window.location.hash='#layout='+'f'.repeat(32);
    resolve(new Response(JSON.stringify({host_layout_handoff:true,vehicle:target}),{headers:{'Content-Type':'application/json'}}));
    await new Promise(setImmediate);
    assert.equal(calls,1);
    assert.deepEqual(f.navigations,[]);
  }finally{global.fetch=original;}
});
test('body deadline aborts a stalled response before any scene import',async()=>{
  const original=global.fetch,f=fixture();let body,signal;
  global.fetch=async(url,options)=>{
    signal=options.signal;
    return new Response(new ReadableStream({start(controller){body=controller;}}),{headers:{'Content-Type':'application/json'}});
  };
  try{
    await assert.rejects((await moduleReady).preparePackageStartup({window:f.window,requestTimeoutMs:5}),/timed out/);
    assert.equal(signal.aborted,true);
    body.close();
    await new Promise(setImmediate);
    assert.deepEqual(f.navigations,[]);
  }finally{global.fetch=original;}
});
test('page exit cancels known preparation without importing scene',async()=>{
  const f=fixture({hook:route=>{if(route==='car-switch')f.events.dispatchEvent(new Event('pagehide'));}});
  assert.equal(await (await moduleReady).preparePackageStartup(f),false);
  assert.equal(f.calls.filter(x=>x[0].endsWith('/cancel')).length,1);
  assert.deepEqual(f.navigations,[]);
});
test('unsafe commit receipt cannot navigate',async()=>{
  const f=fixture({hook:route=>route.endsWith('/commit')?{id:jobId,status:'committed',url:'https://example.com/'}:undefined});
  await assert.rejects((await moduleReady).preparePackageStartup(f),/destination/);
  assert.deepEqual(f.navigations,[]);
});
test('real startup imports the gate before the scene-bearing editor',()=>{
  const html=fs.readFileSync(path.join(web,'index.html'),'utf8');
  assert.ok(html.indexOf("import('./studio-bootstrap.mjs')")>0);
  assert.ok(html.indexOf("import('./studio-bootstrap.mjs')")<html.indexOf("import('./livery-editor.mjs')"));
});
