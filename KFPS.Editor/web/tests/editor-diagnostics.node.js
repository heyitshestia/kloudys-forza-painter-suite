const test = require('node:test');
const assert = require('node:assert/strict');
const {create} = require('../editor-diagnostics.js');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture() {
  let now=0, next=0, frame=null, observer=null;
  const timeouts=new Map(), intervals=new Map();
  const target = () => {
    const handlers = new Map();
    return { handlers, addEventListener(name, fn) { if(!handlers.has(name))handlers.set(name,new Set());handlers.get(name).add(fn); },
      removeEventListener(name, fn) { handlers.get(name)?.delete(fn); },
      emit(name, value) { for(const fn of handlers.get(name)||[])fn(value); },
      listenerCount() { return [...handlers.values()].reduce((sum,set)=>sum+set.size,0); } };
  };
  const document={...target(),visibilityState:'visible',hasFocus:()=>true};
  const env={document,performance:{now:()=>now},crypto:globalThis.crypto,location:{hash:''},sessionStorage:{getItem:()=>null},
    ...target(),requestAnimationFrame:fn=>{frame=fn;return ++next;},cancelAnimationFrame:()=>{frame=null;},
    setTimeout:(fn,delay=0)=>{const id=++next;timeouts.set(id,{fn,at:now+delay});return id;},clearTimeout:id=>timeouts.delete(id),
    setInterval:fn=>{const id=++next;intervals.set(id,fn);return id;},clearInterval:id=>intervals.delete(id),
    AbortController,fetch:async()=>({ok:true,json:async()=>({logging:{written:1,last_write:1}})}),
    PerformanceObserver:class {static supportedEntryTypes=['longtask'];constructor(fn){observer=fn;}observe(){}disconnect(){observer=null;}}};
  const api=create(env);
  return {api,env,timeouts,intervals,setTime:value=>{now=value;},advance:async value=>{
      now=value;for(let pass=0;pass<12;pass++) {for(const [id,timer] of [...timeouts])if(timer.at<=now){timeouts.delete(id);timer.fn();}await Promise.resolve();}
    },frame:value=>{now=value;frame?.(value);},
    visibility:value=>{document.visibilityState=value;document.emit('visibilitychange');},target,
    task:(startTime,duration)=>observer?.({getEntries:()=>[{startTime,duration}]})};
}

test('native close drains after recovery and still rejects edits made during the drain', async()=>{
  const source=fs.readFileSync(require.resolve('../editor.js'),'utf8');
  const operation=source.slice(source.indexOf('async function executeDesktopOperation('),source.indexOf('\nwindow.KfpsDesktop ='));
  assert.ok(operation.startsWith('async function executeDesktopOperation('));
  for(const changes of [false,true]) {
    const order=[], context={editorCommands:{busy:false},pixelArtGenerationRunning:false,textVinylGenerationRunning:false,
      recoveryRestoreDepth:0,editorAssetLibrary:null,documentGeneration:1,overlayRevision:0,
      currentHistoryState:()=>1,flushPendingNudgeHistory:()=>{},flushPendingAutosaveToBrowser:()=>{},
      flushPendingAutosave:async()=>order.push('recovery'),hasEditableWorkspace:()=>true,
      editorRecovery:{status:{serverOk:true}},KfpsI18n:{t:value=>value},
      KfpsEditorPreferences:{flush:async()=>{order.push('settings');return true;}}};
    context.window={KfpsEditorPreferences:context.KfpsEditorPreferences,KfpsEditorDiagnostics:{drain:async()=>{
      order.push('logs');if(changes)context.overlayRevision++;return true;
    }}};
    vm.createContext(context);vm.runInContext(operation,context);
    const result=await context.executeDesktopOperation('close',{action:'keep-recovery'});
    assert.deepEqual(order,['recovery','settings','logs']);assert.equal(result.ok,!changes);
    if(changes)assert.match(result.error,/document changed/);
  }
});

test('close drain aborts a stalled request at its two-second budget and preserves the pending batch',async()=>{
  const f=fixture();
  f.env.fetch=(_url,options)=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Error('aborted'))));
  f.api.configure({headers:{test:'test'}});await Promise.resolve();
  const draining=f.api.drain();await f.advance(2001);
  assert.equal(await draining,false);assert.equal(f.api.snapshot().transportOk,false);
  assert.equal(f.api.snapshot().metrics.clientDrops,0);assert.ok(f.api.snapshot().metrics.queueDepth>0);
  f.api.dispose();assert.equal(f.timeouts.size,0);
});

test('hidden window time is not counted as a visible stall; missing heap stays unavailable',()=>{
  const f=fixture(); f.frame(10);f.frame(26);f.visibility('hidden');f.frame(5000);f.visibility('visible');f.frame(6000);f.frame(6016);
  const metrics=f.api.snapshot().metrics;
  assert.equal(metrics.totalGaps100,0);assert.equal(metrics.frameMax,16);assert.equal('heapBytes' in metrics,false);
  f.api.dispose();assert.equal(f.intervals.size,0);
});

test('selection-only renders do not reuse a stale full-render duration; rebind and dispose remove listeners',()=>{
  const f=fixture(), events=new Map();
  const canvas={lowerCanvasEl:f.target(),upperCanvasEl:f.target(),contextContainer:{},
    on(name,fn){if(!events.has(name))events.set(name,new Set());events.get(name).add(fn);},
    off(name,fn){events.get(name)?.delete(fn);},fire(name,value){for(const fn of events.get(name)||[])fn(value);}};
  f.api.bindCanvas(canvas);f.api.bindCanvas(canvas);
  f.setTime(90);f.api.awaitPaint('settled-paint',{documentId:2,commitId:7});
  f.api.awaitPaint('PRIVATE',{});
  f.setTime(100);canvas.fire('before:render',{ctx:canvas.contextContainer});
  f.setTime(108);canvas.fire('after:render',{ctx:canvas.contextContainer});
  f.setTime(2100);canvas.fire('after:render');
  const m=f.api.snapshot().metrics;
  assert.equal(m.renderCount,1);assert.equal(m.renderMax,8);
  const paint=f.api.snapshot().events.find(e=>e.phase==='settled-paint');
  assert.equal(paint.commitId,7);assert.equal(paint.duration,18);assert.equal(paint.renderDuration,8);
  assert.equal(f.api.snapshot().events.filter(e=>e.kind==='phase').length,1);
  const target={kloudy:{type:27}};
  canvas.fire('object:moving',{target});
  const inputId=f.api.snapshot().events.at(-1).inputId;
  assert.ok(inputId>0);
  f.env.document.emit('pointerup');
  const modified={target};canvas.fire('object:modified',modified);
  assert.equal(modified.kfpsDiagnosticInputId,inputId);
  canvas.fire('object:moving',{target});f.env.document.emit('pointercancel');
  const cancelled={target};canvas.fire('object:modified',cancelled);assert.equal(cancelled.kfpsDiagnosticInputId,0);
  f.env.document.emit('click',{target:{closest:()=>({id:'undoBtn'})}});
  f.api.dispose();
  assert.equal(f.env.listenerCount(),0);assert.equal(f.env.document.listenerCount(),0);
  assert.equal(canvas.lowerCanvasEl.listenerCount(),0);assert.equal(canvas.upperCanvasEl.listenerCount(),0);
  assert.equal([...events.values()].reduce((sum,set)=>sum+set.size,0),0);
  assert.equal(f.timeouts.size,0);f.api.setEnabled(true);f.frame(4000);
  assert.equal(f.api.snapshot().metrics.totalDraws,1);
});

test('error and terminal records survive bounded backlog pressure with explicit critical drops',async()=>{
  const f=fixture();
  f.api.record('js-error',{error:'TypeError',source:'editor.js'});
  f.api.record('command',{state:'committed',seq:15});
  for(let i=0;i<2000;i++)f.api.record('long-task',{duration:60});
  let s=f.api.snapshot();
  assert.ok(s.events.some(e=>e.kind==='js-error'));assert.ok(s.events.some(e=>e.kind==='command'&&e.state==='committed'));
  assert.equal(s.events.length,48);assert.equal(s.metrics.criticalDrops,0);
  for(let i=0;i<1200;i++)f.api.record('js-error',{error:'RangeError'});
  assert.ok(f.api.snapshot().metrics.criticalDrops>0);
  f.api.dispose();
});
test('delayed observer entries retain the action at the time of the stall',()=>{
  const f=fixture();f.setTime(100);f.api.action('rotate');f.setTime(390);f.api.finish();f.setTime(500);f.task(100,280);
  assert.equal(f.api.snapshot().events.at(-1).action,'rotate');
  assert.equal(f.api.snapshot().metrics.totalTasks,1);f.api.dispose();
});

test('disposal aborts transport and ignores late replies without rescheduling',async()=>{
  for(const failed of [false,true]) {
    const f=fixture();let resolve, reject, signal;
    f.env.fetch=(_url,options)=>{signal=options.signal;return new Promise((a,b)=>{resolve=a;reject=b;});};
    f.api.configure({headers:{test:'test'}});
    const pending=f.api.flush();
    await Promise.resolve();
    f.api.dispose();assert.equal(signal.aborted,true);
    if(failed)reject(Error('late failure'));
    else resolve({ok:true,json:async()=>({logging:{written:999}})});
    assert.equal(await pending,false);
    assert.notEqual(f.api.snapshot().logging.written,999);
    assert.equal(f.timeouts.size,0);assert.equal(f.intervals.size,0);
    f.api.record('edit');assert.equal(f.api.snapshot().events.length,0);
  }
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
  for(let i=0;i<1400;i++)f.api.record('edit');
  f.setTime(500);await f.api.flush();
  assert.equal(f.api.snapshot().events.length,48);assert.ok(f.api.snapshot().metrics.clientDrops>=350);
  assert.equal(f.api.snapshot().transportOk,false);
  f.env.fetch=async()=>({ok:true,json:async()=>({logging:{written:4}})});f.setTime(3000);await f.api.flush();
  assert.equal(f.api.snapshot().transportOk,true);assert.equal(f.api.snapshot().logging.written,4);
  f.api.dispose();assert.equal(f.timeouts.size,0);assert.equal(f.intervals.size,0);
});

test('a dense edit burst drains in bounded ordered packets without lost events',async()=>{
  const f=fixture(),sent=[];
  f.env.fetch=async(_url,options)=>{sent.push(options.body);return {ok:true,json:async()=>({accepted:sent.length,logging:{written:sent.length}})};};
  f.api.configure({headers:{test:'test'}});await f.api.flush();
  for(let i=0;i<180;i++)f.api.record('commit',{commitId:i+1,state:'committed'});
  assert.equal(f.api.snapshot().metrics.criticalDrops,0);
  for(let i=1;i<=5;i++){f.setTime(i*300);await f.api.flush();}
  const packets=sent.map(JSON.parse);
  assert.deepEqual(packets.flatMap(p=>p.events).filter(e=>e.kind==='commit').map(e=>e.commitId),Array.from({length:180},(_,i)=>i+1));
  assert.ok(packets.every(p=>p.events.length<=48));
  assert.ok(sent.every(body=>Buffer.byteLength(body)<=24*1024));
  assert.equal(f.api.snapshot().metrics.clientDrops,0);
  assert.equal(f.api.snapshot().metrics.queueDepth,0);
  f.api.dispose();assert.equal(f.timeouts.size,0);
});

test('uncertain delivery retries the exact same batch and sequence before newer events',async()=>{
  const f=fixture(),sent=[];let fail=true;
  f.env.fetch=async(_url,options)=>{sent.push(options.body);if(fail)throw Error('response lost');return {ok:true,json:async()=>({accepted:1,logging:{written:1}})};};
  f.api.record('commit',{commitId:1});f.api.configure({headers:{test:'test'}});await f.api.flush();
  f.api.record('commit',{commitId:2});fail=false;f.setTime(2500);await f.api.flush();
  assert.equal(sent[0],sent[1]);
  f.setTime(2800);await f.api.flush();
  const packets=sent.map(JSON.parse);
  assert.ok(packets[2].seq>packets[1].seq);
  assert.deepEqual(packets[2].events.filter(e=>e.kind==='commit').map(e=>e.commitId),[2]);
  assert.equal(f.api.snapshot().metrics.clientDrops,0);f.api.dispose();
});

test('burst delivery is scheduled without more input and never overlaps requests',async()=>{
  const f=fixture(),packets=[];let active=0,maxActive=0;
  f.env.fetch=async(_url,options)=>{active++;maxActive=Math.max(active,maxActive);packets.push(JSON.parse(options.body));await Promise.resolve();active--;return {ok:true,json:async()=>({accepted:1})};};
  f.api.configure({headers:{test:'test'}});await f.api.flush();
  for(let i=0;i<180;i++)f.api.record('commit',{commitId:i+1});
  for(let ms=250;ms<=1500;ms+=250)await f.advance(ms);
  assert.equal(maxActive,1);
  assert.equal(packets.flatMap(p=>p.events).filter(e=>e.kind==='commit').length,180);
  assert.equal(f.api.snapshot().metrics.queueDepth,0);
  assert.equal(f.api.snapshot().metrics.criticalDrops,0);f.api.dispose();
});

test('large records split by UTF-8 wire bytes and oversized records do not jam following events',async()=>{
  const f=fixture(),sent=[];
  f.env.fetch=async(_url,options)=>{sent.push(options.body);return {ok:true,json:async()=>({accepted:1})};};
  f.api.configure({headers:{test:'test'}});await f.api.flush();
  for(let i=0;i<12;i++)f.api.record('phase',{commitId:i+1,source:'\uAC00'.repeat(1000)});
  f.api.record('phase',{source:'x'.repeat(30000)});f.api.record('commit',{commitId:99});
  for(let i=1;i<=5;i++){f.setTime(i*300);await f.api.flush();}
  assert.ok(sent.every(body=>Buffer.byteLength(body)<=24*1024));
  assert.equal(sent.map(JSON.parse).flatMap(p=>p.events).filter(e=>e.commitId).length,13);
  assert.equal(f.api.snapshot().metrics.clientDrops,1);f.api.dispose();
});

test('close drains recent and queued events without the normal send-rate delay',async()=>{
  const f=fixture(),packets=[];
  f.env.fetch=async(_url,options)=>{packets.push(JSON.parse(options.body));return {ok:true,json:async()=>({accepted:1})};};
  f.api.configure({headers:{test:'test'}});await f.api.flush();
  for(let i=0;i<180;i++)f.api.record('commit',{commitId:i+1});
  assert.equal(await f.api.drain(),true);
  assert.equal(packets.flatMap(p=>p.events).filter(e=>e.kind==='commit').length,180);
  assert.equal(f.api.snapshot().metrics.queueDepth,0);f.api.dispose();
});

test('a synchronous transport failure does not leave the sender permanently pending',async()=>{
  const f=fixture();f.env.fetch=()=>{throw Error('synchronous failure');};
  f.api.configure({headers:{test:'test'}});await f.api.flush();
  f.env.fetch=async()=>({ok:true,json:async()=>({accepted:1})});
  f.setTime(2500);assert.equal(await f.api.flush(),true);
  f.api.dispose();assert.equal(f.timeouts.size,0);
});
