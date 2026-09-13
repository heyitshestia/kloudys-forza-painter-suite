import test from 'node:test';
import assert from 'node:assert/strict';
import {nativeSignIn,signInErrorText} from '../public/native-signin.mjs';
import {korean} from '../public/report-ko.mjs';

const origin='https://support.example';
function fixture({duration=300000,wallOffset=0,api}={}) {
  let elapsed=1000;
  const events=[],tasks=[],accounts=[];
  const id=crypto.randomUUID();
  const response={id,code:'ABCD-1234',url:origin+'/auth/native?ticket='+id,
    expires_at:Date.now()+wallOffset+300000,...(duration===null?{}:{expires_in_ms:duration})};
  const flow=nativeSignIn({origin,now:()=>elapsed,changed:v=>events.push(v),authenticated:v=>accounts.push(v),
    api:api|| (async path=>path.endsWith('/start')?response:{status:'pending'}),
    schedule:fn=>{tasks.push(fn);return tasks.length;},unschedule:()=>{}});
  return {flow,response,events,tasks,accounts,time:value=>{elapsed=value;}};
}

test('clock skew in either direction does not prevent valid new or legacy sign-in',async()=>{
  for(const duration of [300000,null]) for(const wallOffset of [-31536000000,-86400000,-2000,0,2000,86400000,31536000000]) {
    const f=fixture({duration,wallOffset});await f.flow.start();
    assert.equal(f.flow.request().id,f.response.id,`offset ${wallOffset}, duration ${duration}`);
    f.time(300999);assert(f.flow.request());
    f.time(301000);assert.equal(f.flow.request(),null);
    assert.equal(f.events.at(-1).error,'expired');
  }
});

test('wall-clock corrections after starting do not alter the monotonic countdown',async()=>{
  const saved=Date.now;
  try {
    const f=fixture();await f.flow.start();
    for(const offset of [-86400000,86400000]) {Date.now=()=>saved()+offset;assert(f.flow.request());}
    f.time(301000);assert.equal(f.flow.request(),null);
  } finally {Date.now=saved;}
});

test('duration validation, elapsed response and authoritative server expiry remain fail-closed',async()=>{
  for(const duration of [0,-1,300001,Infinity,NaN,'300000',0.5]) {
    const f=fixture({duration});await f.flow.start();assert.equal(f.flow.request(),null);
    assert.equal(f.events.at(-1).error,'invalid-response');
  }
  const f=fixture({duration:2000});await f.flow.start();f.time(3000);
  await f.tasks.shift()();assert.equal(f.flow.request(),null);
  let response;
  const slow=fixture({api:async()=>{slow.time(301001);return response;}});response=slow.response;
  await slow.flow.start();assert.equal(slow.events.at(-1).error,'expired');
  const expired=fixture({api:async path=>path.endsWith('/start')?expired.response:{status:'expired'}});
  await expired.flow.start();await expired.tasks.shift()();
  assert.equal(expired.flow.request(),null);assert.equal(expired.events.at(-1).error,'expired');
});

test('startup errors retain safe reasons and HTTP status, not server text',async()=>{
  for(const [error,reason] of [
    [new TypeError('private network URL'),'network'],
    [new DOMException('private','TimeoutError'),'timeout'],
    [new DOMException('private','AbortError'),'timeout'],
    [Object.assign(Error('private'),{status:429}),'rate-limited'],
    [Object.assign(Error('private'),{status:503}),'service-unavailable'],
    [Object.assign(Error('private'),{status:502}),'server-error'],
    [Object.assign(Error('private'),{status:403}),'request-rejected'],
    [Object.assign(Error('private'),{status:200,supportCode:'invalid-response'}),'invalid-response'],
  ]) {
    const f=fixture({api:async()=>{throw error;}});await f.flow.start();
    assert.equal(f.events.at(-1).error,reason);
    const event=f.flow.diagnostics().at(-1);
    assert.equal(event.stage,'start');assert.equal(event.result,reason);
    assert.equal(event.http_status,error.status||0);
    assert(!JSON.stringify(f.flow.diagnostics()).includes('private'));
  }
});

test('failure retries clear stale errors; no callback logs or submits account data',async()=>{
  let fail=true;
  const f=fixture({api:async path=>{if(fail)throw Error('private');return path.endsWith('/start')?f.response:{status:'ready'};}});
  await f.flow.start();fail=false;await f.flow.start();
  assert(f.flow.request());assert.equal(f.events.at(-1).error,'');
  assert.equal(f.flow.diagnostics().at(-1).attempt,2);
  const copy=f.flow.diagnostics();copy[0].stage='mutated';assert.notEqual(f.flow.diagnostics()[0].stage,'mutated');
});

test('poll recovery distinguishes missing session from transport failure and successful authentication',async()=>{
  let session=false,pollFailure=true;
  const f=fixture({api:async path=>{
    if(path.endsWith('/start'))return f.response;
    if(path.endsWith('/poll')){if(pollFailure)throw new TypeError('private');return {status:'ready'};}
    return {authenticated:session,name:'private-account'};
  }});
  await f.flow.start();await f.tasks.shift()();assert.equal(f.events.at(-1).error,'network');
  pollFailure=false;await f.tasks.shift()();assert.equal(f.events.at(-1).error,'session-missing');
  const count=f.flow.diagnostics().length;
  for(let i=0;i<20;i++)await f.tasks.shift()();
  assert.equal(f.flow.diagnostics().length,count,'repeated missing-session polls do not flood logs');
  session=true;await f.tasks.shift()();assert.equal(f.accounts.length,1);
  assert.equal(f.flow.diagnostics().at(-1).result,'authenticated');
  assert(!JSON.stringify(f.flow.diagnostics()).includes('private-account'));
});

test('diagnostics are bounded, cursor-based and avoid polling spam and credentials',async()=>{
  const f=fixture();await f.flow.start();
  for(let i=0;i<200;i++)await f.tasks.shift()();
  assert.equal(f.flow.diagnostics().filter(e=>e.stage==='poll').length,1);
  f.flow.opened(f.response.id,false);f.flow.manual();
  const since=f.flow.diagnostics().at(-1).sequence;
  assert.deepEqual(f.flow.diagnostics(since),[]);
  for(let i=0;i<100;i++){f.flow.reopen();f.flow.manual();}
  assert.equal(f.flow.diagnostics().length,64);
  const serialized=JSON.stringify(f.flow.diagnostics());
  for(const secret of [f.response.id,f.response.url,f.response.code,'expires_at'])assert(!serialized.includes(secret));
  for(const event of f.flow.diagnostics())assert.deepEqual(Object.keys(event).sort(),['attempt','elapsed_ms','http_status','result','sequence','stage']);
});

test('all specific error messages and pending states have Korean translations',()=>{
  for(const error of ['expired','denied','cancelled','rate-limited','service-unavailable','invalid-response',
    'request-rejected','server-error','session-missing','timeout','network','browser']) {
    for(const id of [undefined,'fixture'])assert(korean[signInErrorText({error,id})],error);
  }
  assert(korean['Starting Discord sign-in...']);
  assert(korean['Authorize in your browser, then return to KFPS. Your report has not been sent.']);
});
