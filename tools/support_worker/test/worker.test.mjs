import test, {afterEach, beforeEach} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {gzipSync} from 'node:zlib';
import {NUMBERS, BOOLS, ASSETS, ENUMS, normalizeEditor} from '../public/editor-diagnostics.mjs';
import worker, {ReportStore, sign, verify} from '../src/worker.mjs';
import {SCHEMA, normalizeReport, readJsonLimited, validWebhook, publicSummary, redact} from '../public/protocol.mjs';
import {describeScreenshot} from '../public/screenshots.mjs';
import {describePrivateLogs} from '../public/private-logs.mjs';
import {submissionBody} from '../src/submission.mjs';
import {logBlob,logMetadata} from './log-fixture.mjs';

const originalFetch = globalThis.fetch;
beforeEach(() => { globalThis.fetch = async () => { throw new Error('Unmocked outbound request forbidden in backend tests.'); }; });
afterEach(() => { globalThis.fetch = originalFetch; });
const secret = 'test-only-not-a-real-secret-1234567890';
const user = {id: '111111111111111111', name: 'Synthetic Tester'};
const env = () => ({PUBLIC_ORIGIN: 'https://support.example', SESSION_SECRET: secret, DISCORD_CLIENT_ID: '222222222222222222', DISCORD_CLIENT_SECRET: 'test-client', DELIVERY_ENABLED: '1', DISCORD_GUILD_ID: '333333333333333333', SUPPORT_CHANNEL_ID: '444444444444444444', PRIVATE_CHANNEL_ID: '555555555555555555', PUBLIC_WEBHOOK_URL: 'https://discord.com/api/webhooks/666666666666666666/' + 'a'.repeat(40), PRIVATE_WEBHOOK_URL: 'https://discord.com/api/webhooks/777777777777777777/' + 'b'.repeat(40), DISCORD_JOIN_URL: 'https://discord.com/channels/333333333333333333/444444444444444444'});
const report = () => normalizeReport({schema: SCHEMA, id: crypto.randomUUID(), created_at: '2026-09-06T12:00:00Z', feature: 'Editor', title: 'Synthetic test', description: 'Dragging shapes becomes slow.', technical: {app: {version: '3.1.60'}, hardware: {gpus: [{name: 'Synthetic GPU'}]}},private_logs:logMetadata});
class Storage {
  constructor() { this.data = new Map(); }
  async get(k) { return structuredClone(this.data.get(k)); }
  async put(k, v) { if (typeof k === 'object') { for (const [a,b] of Object.entries(k)) this.data.set(a,structuredClone(b)); } else this.data.set(k, structuredClone(v)); }
  async delete(k) { for (const key of Array.isArray(k) ? k : [k]) this.data.delete(key); }
  async list({prefix}) { return new Map([...this.data].filter(([k]) => k.startsWith(prefix))); }
  async setAlarm(t) { this.alarm = t; }
  async getAlarm() { return this.alarm ?? null; }
}
function fixture() {
  const e = env(), storage = new Storage(), ctx = {storage}, object = new ReportStore(ctx, e), calls = [];
  e.REPORTS = {idFromName: id => id, get: id => { assert.equal(id, user.id); return object; }};
  globalThis.fetch = async (url, options = {}) => {
    const privateChannel = String(url).includes('777777777777777777');
    calls.push({url: String(url), options, kind: privateChannel ? 'private' : 'public'});
    if (options.method !== 'POST') return Response.json({type:1, guild_id: e.DISCORD_GUILD_ID, channel_id: privateChannel ? e.PRIVATE_CHANNEL_ID : e.SUPPORT_CHANNEL_ID});
    return Response.json({id: '888888888888888888', channel_id: privateChannel ? e.PRIVATE_CHANNEL_ID : '999999999999999999'});
  };
  return {e, storage, ctx, object, calls};
}
async function request(e, data, extra = {}, logs = logBlob) {
  const token = await sign({...user, kind:'session', csrf:'csrf-test', exp:Date.now()+60000}, secret);
  const body = data.private_logs ? submissionBody(data,[],logs) : JSON.stringify(data);
  return worker.fetch(new Request(e.PUBLIC_ORIGIN + '/api/reports', {method:'POST', headers:{...(!data.private_logs?{'Content-Type':'application/json'}:{}), Origin:e.PUBLIC_ORIGIN, Cookie:`kfps_support=${token}`, 'X-CSRF-Token':'csrf-test', ...extra}, body}),e);
}
const send = (object, r) => {
  const body=submissionBody(r,[],logBlob);body.set('user',JSON.stringify(user));
  return object.fetch(new Request('https://report.internal/send', {method:'POST',body}));
};

test('save correlation retains only canonical request identifiers and bounded numeric fields', () => {
  const id='358cd0bc-4e38-4bcc-8400-d3fe4e8b6b72';
  const result=normalizeEditor({schema:'kfps-editor-diagnostics/1',recent:[
    {kind:'job',job:'saveProject',state:'committed',requestId:id,jobId:3,documentGeneration:2,queueDepth:0,source:'native',private:'PRIVATE'},
    {kind:'job',job:'saveExport',requestId:'PRIVATE',jobId:'PRIVATE',duration:Infinity},
  ]});
  assert.equal(result.recent[0].requestId,id);
  assert.equal(result.recent[0].jobId,3);
  assert.equal(result.recent[0].source,'native');
  assert.equal(result.recent[1].requestId,undefined);
  assert.equal(result.recent[1].duration,undefined);
  assert.equal(JSON.stringify(result).includes('PRIVATE'),false);
});

test('Python diagnostic contract and browser/server allowlists stay aligned', () => {
  const root = fileURLToPath(new URL('../../../', import.meta.url));
  const output = execFileSync(process.platform === 'win32' ? 'py' : 'python3', [...(process.platform === 'win32' ? ['-3.12'] : []), '-c',
    'import json; from tools.fabric_editor_diagnostics import NUMBERS, BOOLS, ASSETS, ENUMS; print(json.dumps(dict(numbers=sorted(NUMBERS), bools=sorted(BOOLS), assets=sorted(ASSETS), enums={k:sorted(v) for k,v in ENUMS.items()})))'], {cwd: root, encoding: 'utf8'});
  const contract = JSON.parse(output);
  assert.deepEqual([...NUMBERS].sort(), contract.numbers);
  assert.deepEqual([...BOOLS].sort(), contract.bools);
  assert.deepEqual([...ASSETS].sort(), contract.assets);
  assert.deepEqual(Object.fromEntries(Object.entries(ENUMS).map(([k,v]) => [k,[...v].sort()])), contract.enums);
});

test('accepted commit and checkpoint ranges survive collection without arbitrary text', () => {
  const cause={pageId:'a'.repeat(32),documentId:2,commitId:7,firstCommitId:4,operationId:7,commandId:3,historyId:9};
  const result=normalizeEditor({schema:'kfps-editor-diagnostics/1',recent:[
    {kind:'commit',...cause,state:'committed'},
    {kind:'checkpoint',...cause,state:'committed',source:'native',revision:123},
    {kind:'recovery-result',...cause,revision:123,errorCode:'http_error',serverOk:false,browserOk:true},
    {kind:'phase',phase:'settled-paint',...cause,duration:20,renderDuration:12},
    {kind:'job',pageId:'PRIVATE',errorCode:'PRIVATE',phase:'PRIVATE'},
    {kind:'phase',phase:'document-cache',...cause,state:'finished',duration:1300,layers:2900},
  ]});
  for(const event of result.recent.slice(0,4)) for(const [key,value] of Object.entries(cause)) assert.equal(event[key],value);
  assert.equal(result.recent[2].errorCode,'http_error');
  assert.equal(result.recent[3].renderDuration,12);
  assert.deepEqual(result.recent[4],{kind:'job'});
  assert.equal(result.recent[5].phase,'document-cache');
  assert.equal(result.recent[5].layers,2900);
});

test('real Python disk-log report survives review and private attachment, never public post', async () => {
  const root = fileURLToPath(new URL('../../../', import.meta.url));
  const code = `import base64, json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, 'KFPS.UI/src')
from kfps_ui.support_report import build_support_report
from kfps_ui.support_log_bundle import collect_retained_log_bundle
from tools.fabric_editor_diagnostics import EditorDiagnostics
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory)
 runtime=root/'runtime/fabric-editor'
 runtime.mkdir(parents=True)
 (runtime/'desktop.log').write_text('Error: GPU reset\\nsession_token=DO_NOT_SEND\\ndata:image/png;base64,AAAA\\n')
 logger=EditorDiagnostics(root, runtime)
 logger.accept({'schema':1,'page':'a'*32,'seq':1,'metrics':{'frameMax':280,'frameP50':16.700000762939453},'state':{'layers':355,'objects':410,'zoom':1.4562381520517451,'editorRevision':2026091101},'events':[{'kind':'long-task','duration':27.199999999720603,'action':'rotate','message':'DO_NOT_SEND'}]})
 logger.close()
 studio=root/'tools/livery-studio/runs/diagnostics'
 studio.mkdir(parents=True)
 good={'schema_version':1,'utc':'2026-10-19T12:00:00Z','session':'a'*16,'sequence':1,'event':'render','shape_count':3000,'frame_ms':18.5}
 (studio/'studio.jsonl').write_text(json.dumps(good)+'\\n'+json.dumps({**good,'project':'DO_NOT_SEND'})+'\\n')
 report=build_support_report(root, {'page':'editor','log':'Synthetic app error','services':{'editor':{'lastError':'Dragging shapes becomes slow.'}}}, since=time.time()-20, collect=lambda:{})
 attachment=collect_retained_log_bundle(root,snapshot=report['technical'])
 report['private_logs']=attachment[0]
 print(json.dumps({'report':report,'logs':base64.b64encode(attachment[1]).decode('ascii')}))`;
  const prepared = JSON.parse(execFileSync(process.platform === 'win32' ? 'py' : 'python3', [...(process.platform === 'win32' ? ['-3.12'] : []), '-c', code], {cwd: root, encoding: 'utf8'}));
  const raw=prepared.report, retained=new Blob([Buffer.from(prepared.logs,'base64')],{type:'application/gzip'});
  const collected=(await describePrivateLogs(retained,{redact})).bundle;
  const studio=collected.files.find(f=>f.name==='studio-performance-0000.log');
  assert(studio, 'The actual installed collector must include Studio diagnostics');
  assert.equal(studio.omitted_lines,1);
  assert.equal(JSON.parse(studio.text).shape_count,3000);
  assert(!JSON.stringify(collected).includes('DO_NOT_SEND'));
  raw.technical.logs.push(...Array.from({length: 8}, (_, i) => ({source: `worker-${i}`, text: `Error: worker ${i} failed`, age_seconds: 25, previous_session: true})));
  const reviewed = normalizeReport(raw);
  assert.deepEqual(normalizeReport(reviewed), reviewed);
  assert.equal(reviewed.technical.logs.length, 10);
  assert.equal(reviewed.technical.editor.page.metrics.frameMax, 280);
  assert.equal(reviewed.technical.editor.page.metrics.frameP50, 16.700000762939453);
  assert.equal(reviewed.technical.editor.page.state.layers, 355);
  assert.equal(reviewed.technical.editor.page.state.objects, 410);
  assert.equal(reviewed.technical.editor.recent[0].action, 'rotate');
  assert.equal(JSON.stringify(reviewed).includes('DO_NOT_SEND'), false);
  const f = fixture();
  const response=await request(f.e, reviewed,{},retained);
  assert.equal((await response.json()).status, 'delivered');
  const posts = f.calls.filter(c => c.options.method === 'POST');
  const attachment = JSON.parse(await posts[0].options.body.get('files[0]').text());
  assert.deepEqual(attachment.technical.editor, reviewed.technical.editor);
  assert.deepEqual(attachment.technical.logs, reviewed.technical.logs);
  assert.deepEqual(Buffer.from(await posts[0].options.body.get('files[1]').arrayBuffer()),Buffer.from(await retained.arrayBuffer()));
  assert.equal(posts[1].options.body.includes('GPU reset'), false);
  assert.equal(posts[1].options.body.includes('worker-7'), false);
  assert.equal(posts[1].options.body.includes('studio-performance'), false);
});

test('diagnostics drop unknown text, wrong types and nonfinite numbers; logs remain bounded', () => {
  const r = report();
  r.technical.editor = {schema:'kfps-editor-diagnostics/1', age_seconds:Infinity, native:{rssBytes:NaN, code:'PRIVATE', ready:true},
    page:{page:'a'.repeat(32),seq:1,metrics:{frameMax:280,heapBytes:'PRIVATE'},state:{layers:355,title:'PRIVATE'},events:[{kind:'js-error',error:'TypeError',source:'PRIVATE',message:'PRIVATE'}]},
    installed_assets:{'editor.js':'a'.repeat(64),'PRIVATE':'b'.repeat(64)},logging:{failed:true,password:'PRIVATE'},recent:[]};
  r.technical.logs = Array.from({length:100}, () => ({source:'worker',text:'\uc624\ub958 '.repeat(5000)}));
  const clean = normalizeReport(r);
  assert.equal(JSON.stringify(clean).includes('PRIVATE'), false);
  assert.equal(clean.technical.editor.page.metrics.frameMax, 280);
  r.technical.editor.native = JSON.parse('{"__proto__":"PRIVATE","constructor":"PRIVATE","toString":"PRIVATE","ready":true}');
  assert.deepEqual(normalizeReport(r).technical.editor.native, {ready:true});
  assert.equal(clean.technical.editor.installed_assets['editor.js'], 'a'.repeat(64));
  assert.equal(clean.technical.logs.length, 16);
  assert.ok(clean.technical.logs.reduce((sum,e)=>sum+Buffer.byteLength(e.text),0) <= 28000);
  assert.ok(Buffer.byteLength(JSON.stringify(clean)) < 65536);
  r.include_technical=false; assert.deepEqual(normalizeReport(r).technical, {});
});

test('allowlist drops artwork, credentials, local paths and unknown fields on both sides', () => {
  assert.equal(redact('Selected: Private Contest Entry.json').includes('Private Contest'),false);
  const r = report(); r.technical.artwork = {shapes:[1]}; r.technical.logs = [{source:'app',text:'Password: never-send\nFailed C:\\Users\\Private Name\\secret-work.json\nEmail private@example.test\nhttps://example.test/private?token=123'}];
  r.technical.hardware.serial = 'private-serial'; r.source = 'untrusted';
  const clean = normalizeReport(r), text = JSON.stringify(clean);
  for (const value of ['never-send','Private Name','private@example','example.test/private','private-serial','"artwork"']) assert.equal(text.includes(value),false, value);
  assert.equal(clean.source,'discord-form'); assert.equal(clean.technical.hardware.gpus[0].name,'Synthetic GPU');
});
test('legacy drafts do not gain empty diagnostic fields that change receipt hashes', () => {
  const legacy = report();
  assert.equal('editor' in legacy.technical, false);
  assert.equal('log_collection' in legacy.technical, false);
  legacy.technical.logs = Array.from({length:5}, (_,i)=>({source:`worker-${i}`,text:'Error: short repeated line\n'.repeat(250).slice(0,6500)}));
  const first=normalizeReport(legacy);
  assert.deepEqual(first.technical.logs,legacy.technical.logs);
  assert.deepEqual(normalizeReport(first),first);
});
test('excluding technical details removes them entirely', () => { const r=report(); r.include_technical=false; assert.deepEqual(normalizeReport(r).technical,{}); });
test('public KFPS version survives technical opt-out without restoring private context', () => {
  const clean=normalizeReport({...report(),include_technical:false,kfps_version:' 3.2.4 '});
  assert.equal(clean.kfps_version,'3.2.4');
  assert.deepEqual(clean.technical,{});
  assert.equal('private_logs' in clean,false);
  assert.deepEqual(normalizeReport(clean),clean);
  assert.match(publicSummary(clean,user),/KFPS 3\.2\.4/);
  assert.match(publicSummary(clean,user),/Technical details were not included\./);
  const checked=normalizeReport({...report(),kfps_version:'3.2.4'});
  assert.match(publicSummary(checked,user),/KFPS 3\.2\.4/);
  assert.match(publicSummary(report(),user),/KFPS 3\.1\.60/);
});
test('public KFPS version is optional bounded text using the existing privacy filter', () => {
  for(const value of [undefined,null,false,42,{},[],'','   ']) {
    assert.equal('kfps_version' in normalizeReport({...report(),kfps_version:value}),false);
  }
  assert.equal(normalizeReport({...report(),kfps_version:'x'.repeat(100)}).kfps_version,'x'.repeat(30));
  const clean=normalizeReport({...report(),kfps_version:'Password: do-not-publish'});
  assert.equal(clean.kfps_version,redact('Password: do-not-publish',30));
  assert.equal(JSON.stringify(clean).includes('do-not-publish'),false);
});
test('legacy frozen reports keep exact payloads and receipt hashes on retry without a public KFPS version', async () => {
  for(const included of [true,false]) {
    const f=fixture(),legacy=normalizeReport({...report(),include_technical:included});
    assert.equal('kfps_version' in legacy,false);
    const frozen=JSON.stringify(legacy);
    const hash=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(frozen))).toString('base64url');
    assert.equal(JSON.stringify(normalizeReport(JSON.parse(frozen))),frozen);
    await f.storage.put('report:'+legacy.id,{id:legacy.id,hash,created:Date.now(),private:{state:'sent'},public:{state:'pending'},attempts:1});
    const response=await request(f.e,JSON.parse(frozen));
    assert.equal(response.status,200);
    assert.equal((await response.json()).status,'delivered');
    assert.equal((await f.storage.get('report:'+legacy.id)).hash,hash);
    assert.equal(f.calls.filter(c=>c.kind==='private'&&c.options.method==='POST').length,0);
    const payload=JSON.parse(f.calls.find(c=>c.kind==='public'&&c.options.method==='POST').options.body);
    assert.match(payload.content,included?/KFPS 3\.1\.60/:/KFPS not supplied/);
  }
});
test('long unbroken log lines are processed in bounded time', () => {const start=performance.now(); redact('x'.repeat(1000000)); assert.ok(performance.now()-start<1000);});
test('invalid report formats and oversized request streams fail closed', async () => {
  assert.throws(() => normalizeReport({shapes:[]})); assert.throws(() => normalizeReport({...report(), id:'../../bad'}));
  await assert.rejects(readJsonLimited(new Request('https://example.test',{method:'POST',headers:{'Content-Type':'application/json'},body:'x'.repeat(65537)})));
  await assert.rejects(readJsonLimited(new Request('https://example.test',{method:'POST',body:'{}'})));
});
test('webhooks are pinned to Discord and public text cannot ping members', () => {
  assert.equal(validWebhook(env().PUBLIC_WEBHOOK_URL),true);
  for (const url of ['http://discord.com/api/webhooks/1/x','https://evil.test/api/webhooks/666666666666666666/'+'x'.repeat(40),env().PUBLIC_WEBHOOK_URL+'?thread_id=123']) assert.equal(validWebhook(url),false);
  const r=report(); r.description='@everyone **test**'; assert.equal(publicSummary(r,user).includes('@everyone'),false);
});
test('signed sessions reject tampering, expired and wrong-key cookies', async () => {
  const value={exp:Date.now()+10000,kind:'session'}, token=await sign(value,secret);
  assert.deepEqual(await verify(token,secret),value); assert.equal(await verify(token+'x',secret),null);
  assert.equal(await verify(token,secret,Date.now()+20000),null); assert.equal(await verify(token,secret+'other'),null);
});
test('authorization, CSRF, origin and disabled delivery block before any Discord request', async () => {
  const f=fixture();
  assert.equal((await worker.fetch(new Request(f.e.PUBLIC_ORIGIN+'/api/reports',{method:'POST'}),f.e)).status,401);
  assert.equal((await request(f.e,report(),{'X-CSRF-Token':'wrong'})).status,403);
  assert.equal((await request(f.e,report(),{Origin:'https://evil.test'})).status,403);
  f.e.DELIVERY_ENABLED='0'; assert.equal((await request(f.e,report())).status,503); assert.equal(f.calls.length,0);
});
test('OAuth requests identity only and callback state is mandatory', async () => {
  const e=env(), start=await worker.fetch(new Request(e.PUBLIC_ORIGIN+'/auth/start'),e);
  const location=new URL(start.headers.get('location')); assert.equal(location.searchParams.get('scope'),'identify');
  const cookies=start.headers.get('set-cookie'); assert.match(cookies,/HttpOnly/); assert.match(cookies,/Secure/); assert.match(cookies,/SameSite=Lax/);
  const callback=await worker.fetch(new Request(e.PUBLIC_ORIGIN+'/auth/callback?state=wrong&code=bad'),e);
  assert.match(callback.headers.get('location'),/auth=cancelled/);
});
test('OAuth callback creates an identity-only session without retaining tokens', async () => {
  const e=env(), nonce='test-nonce', signed=await sign({kind:'oauth',nonce,exp:Date.now()+60000},secret);
  const calls=[];
  globalThis.fetch=async(url,options)=>{
    calls.push({url:String(url),options});
    return String(url).endsWith('/token') ? Response.json({access_token:'private-oauth-token',token_type:'Bearer',scope:'identify'}) : Response.json({...user,username:'tester'});
  };
  const response=await worker.fetch(new Request(e.PUBLIC_ORIGIN+'/auth/callback?state='+nonce+'&code=test-code',{headers:{Cookie:`kfps_oauth=${signed}`}}),e);
  assert.equal(response.headers.get('location'),e.PUBLIC_ORIGIN+'/');
  const cookies=response.headers.get('set-cookie'); assert.match(cookies,/kfps_support=/); assert.equal(cookies.includes('private-oauth-token'),false);
  const token=cookies.match(/kfps_support=([^;]+)/)[1], account=await verify(token,secret);
  assert.equal(account.id,user.id); assert.equal(account.kind,'session'); assert.equal(calls.length,2);
  assert.equal(calls[0].options.body.get('redirect_uri'),e.PUBLIC_ORIGIN+'/auth/callback');
});
test('OAuth failures expose only a fixed phase and status, never response bodies', async () => {
  const e=env(), nonce='test-nonce', signed=await sign({kind:'oauth',nonce,exp:Date.now()+60000},secret);
  globalThis.fetch=async()=>new Response('private-response-containing-tokens',{status:401});
  const response=await worker.fetch(new Request(e.PUBLIC_ORIGIN+'/auth/callback?state='+nonce+'&code=private-code',{headers:{Cookie:`kfps_oauth=${signed}`}}),e);
  assert.equal(response.headers.get('location'),e.PUBLIC_ORIGIN+'/?auth=failed&detail=token-request-401');
  assert.equal(JSON.stringify([...response.headers]).includes('private-'),false);
});
test('real route sends private attachment and public forum post then deduplicates', async () => {
  const f=fixture(), r=report();
  assert.equal((await (await request(f.e,r)).json()).status,'delivered');
  assert.equal((await (await request(f.e,r)).json()).status,'delivered');
  const posts=f.calls.filter(c=>c.options.method==='POST'); assert.equal(posts.length,2);
  assert.equal(posts[0].kind,'private'); assert.ok(posts[0].options.body instanceof FormData);
  const attachment=JSON.parse(await posts[0].options.body.get('files[0]').text()); assert.equal(attachment.reporter.id,user.id); assert.equal(attachment.id,r.id);
  assert.equal(JSON.stringify(await f.storage.get('report:'+r.id)).includes('Synthetic GPU'),false);
  const publicPost=JSON.parse(posts[1].options.body); assert.ok(publicPost.thread_name); assert.deepEqual(publicPost.allowed_mentions,{parse:[]}); assert.equal(publicPost.content.includes('Synthetic GPU'),false);
});
test('changed retry body is rejected and parallel clicks do not duplicate', async () => {
  const f=fixture(), r=report();
  const a=await Promise.all([request(f.e,r),request(f.e,r),request(f.e,r)]);
  assert.ok(a.every(v=>v.status===200)); assert.equal(f.calls.filter(c=>c.options.method==='POST').length,2);
  assert.equal((await request(f.e,{...r,description:'Changed contents'})).status,409);
});
test('wrong configured channel cannot receive private diagnostics', async () => {
  const f=fixture(), fetch=globalThis.fetch;
  globalThis.fetch=async(url,opts)=>{ const response=await fetch(url,opts); if(opts?.method!=='POST') return Response.json({type:1,guild_id:f.e.DISCORD_GUILD_ID,channel_id:'123123123123123123'}); return response; };
  assert.equal((await (await request(f.e,report())).json()).status,'blocked'); assert.equal(f.calls.filter(c=>c.options.method==='POST').length,0);
});
test('checked missing archives never reach either destination or create a receipt',async()=>{
  const f=fixture(),r=report();delete r.private_logs;
  assert.equal((await request(f.e,r)).status,400);
  const internal=await f.object.fetch(new Request('https://report.internal/send',{method:'POST',body:JSON.stringify({report:r,user})}));
  assert.equal(internal.status,400);assert.equal(f.calls.length,0);
  assert.equal(await f.storage.get('report:'+r.id),undefined);
  const explicit={...normalizeReport({...r,include_technical:false}),kfps_version:'3.2.4'};
  assert.equal((await(await request(f.e,explicit)).json()).status,'delivered');
  const body=f.calls.find(c=>c.kind==='private'&&c.options.method==='POST').options.body;
  assert.equal(body.get('files[1]'),null);
  const received=JSON.parse(await body.get('files[0]').text());
  assert.deepEqual(received.technical,{});
  assert.equal(received.kfps_version,'3.2.4');
  assert.equal('private_logs' in received,false);
  const summary=JSON.parse(f.calls.find(c=>c.kind==='public'&&c.options.method==='POST').options.body).content;
  assert.match(summary,/KFPS 3\.2\.4/);
  assert.match(summary,/Technical details were not included\./);
});
test('failed private upload cannot publish a summary-only checked report',async()=>{
  const f=fixture(),r=report(),fetch=globalThis.fetch;let observed=0;
  globalThis.fetch=async(url,opts)=>{
    if(opts?.method==='POST'){
      assert(String(url).includes('777777777777777777'));
      assert.deepEqual(Buffer.from(await opts.body.get('files[1]').arrayBuffer()),Buffer.from(await logBlob.arrayBuffer()));
      observed++;return new Response('{}',{status:429});
    }
    return fetch(url,opts);
  };
  assert.equal((await(await request(f.e,r)).json()).status,'retryable');
  assert.equal(observed,1);
  const state=await f.storage.get('report:'+r.id);
  assert.equal(state.private.state,'pending');assert.equal(state.public.state,'pending');
});
test('lost POST acknowledgment and restarted sending state never automatically repost', async () => {
  const f=fixture(), r=report(), fetch=globalThis.fetch;
  globalThis.fetch=async(url,opts)=>{ if(opts?.method==='POST') throw new Error('timeout after remote acceptance'); return fetch(url,opts); };
  assert.equal((await (await request(f.e,r)).json()).status,'uncertain');
  const before=f.calls.length; const restarted=new ReportStore(f.ctx,f.e);
  assert.equal((await (await send(restarted,r)).json()).status,'uncertain'); assert.equal(f.calls.length,before);
  const stored=await f.storage.get('report:'+r.id); stored.private.state='sending'; await f.storage.put('report:'+r.id,stored);
  assert.equal((await (await send(restarted,r)).json()).status,'uncertain');
});
test('partial 429 retry posts only the unfinished destination', async () => {
  const f=fixture(), r=report(), fetch=globalThis.fetch; let reject=true;
  globalThis.fetch=async(url,opts)=>{ if(opts?.method==='POST'&&String(url).includes('666666666666666666')&&reject) {reject=false; return new Response('{}',{status:429});} return fetch(url,opts); };
  assert.equal((await (await request(f.e,r)).json()).status,'retryable');
  const stored=await f.storage.get('report:'+r.id); stored.retryAt=0; await f.storage.put('report:'+r.id,stored);
  assert.equal((await (await request(f.e,r)).json()).status,'delivered');
  assert.equal(f.calls.filter(c=>c.kind==='private'&&c.options.method==='POST').length,1);
});
test('three reports per ten minutes and thirty-day retention', async () => {
  const f=fixture(); for(let i=0;i<3;i++) assert.equal((await request(f.e,report())).status,200);
  assert.equal((await request(f.e,report())).status,429);
  for(const[k,v]of await f.storage.list({prefix:'report:'})) {v.created=Date.now()-31*86400000; await f.storage.put(k,v);}
  await f.object.alarm(); assert.equal((await f.storage.list({prefix:'report:'})).size,0);
});
test('status is scoped to authenticated account and raw context is not returned', async () => {
  const f=fixture(), r=report(); await request(f.e,r);
  const token=await sign({...user,kind:'session',csrf:'c',exp:Date.now()+10000},secret);
  const response=await worker.fetch(new Request(f.e.PUBLIC_ORIGIN+'/api/reports/'+r.id,{headers:{Cookie:`kfps_support=${token}`}}),f.e);
  const text=await response.text(); assert.equal(text.includes('Synthetic GPU'),false); assert.equal(text.includes('Dragging shapes'),false); assert.match(text,/delivered/);
});

async function screenshotFixture() {
  const png=new Blob([Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aipkAAAAASUVORK5CYII=','base64')],{type:'image/png'});
  const r=normalizeReport({...report(),screenshots:[await describeScreenshot(png)],screenshots_public:true});
  return {r,png};
}
async function upload(e,r,files,extra={}) {
  const token=await sign({...user,kind:'session',csrf:'csrf-test',exp:Date.now()+60000},secret);
  return worker.fetch(new Request(e.PUBLIC_ORIGIN+'/api/reports',{method:'POST',headers:{Origin:e.PUBLIC_ORIGIN,Cookie:`kfps_support=${token}`,'X-CSRF-Token':'csrf-test',...extra},body:submissionBody(r,files,logBlob)}),e);
}
test('real screenshot route publishes images only with the public post and deduplicates',async()=>{
  const f=fixture(),{r,png}=await screenshotFixture();
  const results=await Promise.all([upload(f.e,r,[png]),upload(f.e,r,[png])]);
  for(const response of results)assert.equal((await response.json()).status,'delivered');
  const posts=f.calls.filter(c=>c.options.method==='POST');assert.equal(posts.length,2);
  const privateBody=posts[0].options.body;
  assert.equal([...privateBody.keys()].filter(k=>k.startsWith('files')).length,2);
  assert.equal(privateBody.get('files[0]').type,'application/json');
  assert.deepEqual(Buffer.from(await privateBody.get('files[1]').arrayBuffer()),Buffer.from(await logBlob.arrayBuffer()));
  const publicBody=posts[1].options.body,payload=JSON.parse(publicBody.get('payload_json'));
  assert.deepEqual(Buffer.from(await publicBody.get('files[0]').arrayBuffer()),Buffer.from(await png.arrayBuffer()));
  assert.match(payload.content,/shared publicly/);assert(!payload.content.includes('Synthetic GPU'));
  assert.equal(payload.attachments[0].filename,'screenshot-1.png');assert.deepEqual(payload.allowed_mentions,{parse:[]});
  const stored=JSON.stringify(await f.storage.get('report:'+r.id));
  assert(!stored.includes('screenshots'));assert(!stored.includes('Synthetic GPU'));
});
test('screenshot validation and auth failures never post to Discord',async()=>{
  const f=fixture(),{r,png}=await screenshotFixture();
  assert.equal((await upload(f.e,r,[png],{'X-CSRF-Token':'wrong'})).status,403);
  assert.equal((await upload(f.e,{...r,screenshots_public:false},[png])).status,400);
  assert.equal((await upload(f.e,r,[])).status,400);
  assert.equal(f.calls.length,0);
});
test('partial screenshot delivery requires the same images and skips the delivered private part',async()=>{
  const f=fixture(),{r,png}=await screenshotFixture(),fetch=globalThis.fetch;
  let reject=true;
  globalThis.fetch=async(url,opts)=>opts?.method==='POST'&&String(url).includes('666666666666666666')&&reject
    ?(reject=false,new Response('{}',{status:429})):fetch(url,opts);
  assert.equal((await(await upload(f.e,r,[png])).json()).status,'retryable');
  const stored=await f.storage.get('report:'+r.id);stored.retryAt=0;await f.storage.put('report:'+r.id,stored);
  const before=f.calls.length;
  assert.equal((await upload(f.e,r,[])).status,400);assert.equal(f.calls.length,before);
  assert.equal((await(await upload(f.e,r,[png])).json()).status,'delivered');
  assert.equal(f.calls.filter(c=>c.kind==='private'&&c.options.method==='POST').length,1);
});

test('malformed private log JSON never appears in the HTTP error response', async () => {
  const f=fixture(), r=report();
  for (const raw of ['PRIVATE-ARCHIVE-CONTENT', JSON.stringify({schema:r.private_logs.schema,created_at:'2026-11-13T12:00:00Z',
    files:[{name:'performance.jsonl',modified_utc:'2026-11-13T12:00:00Z',source_bytes:100,omitted_lines:0,text:'PRIVATE-EVENT-CONTENT'}],warnings:[]})]) {
    const logs=new Blob([gzipSync(raw)],{type:'application/gzip'});
    const response=await request(f.e,r,{},logs);
    assert.equal(response.status,400);
    const value=await response.json();
    assert.equal(value.error,'Invalid private application log attachment.');
    assert.equal(response.headers.get('cache-control'),'no-store');
  }
  assert.equal(f.calls.length,0);
  assert.equal(await f.storage.get('report:'+r.id),undefined);
});

for (const operation of ['submission','json submission','status']) test(`actor transport failure returns a safe JSON ${operation} response`, async () => {
  const f=fixture(), r=report();
  f.e.REPORTS.get=()=>({fetch:async()=>{throw new Error('PRIVATE-TRANSPORT-DETAIL');}});
  let response;
  if(operation==='submission') response=await request(f.e,r);
  else if(operation==='json submission') response=await request(f.e,normalizeReport({...r,include_technical:false}));
  else {
    const token=await sign({...user,kind:'session',csrf:'csrf-test',exp:Date.now()+60000},secret);
    response=await worker.fetch(new Request(f.e.PUBLIC_ORIGIN+'/api/reports/'+r.id,{headers:{Cookie:`kfps_support=${token}`}}),f.e);
  }
  assert.equal(response.status,503);
  assert.equal(response.headers.get('cache-control'),'no-store');
  assert.equal((await response.text()).includes('PRIVATE-TRANSPORT-DETAIL'),false);
  assert.equal(f.calls.length,0);
});

test('private and public destinations cannot be configured to the same channel', async () => {
  const f=fixture();
  f.e.PRIVATE_CHANNEL_ID=f.e.SUPPORT_CHANNEL_ID;
  assert.equal((await (await request(f.e,report())).json()).status,'blocked');
  assert.equal(f.calls.length,0,'configuration is rejected before contacting either destination');
});

for (const phase of ['preflight','post']) test(`rate-limited ${phase} preserves the upstream retry window across restart`, async () => {
  const f=fixture(), r=report(), fetch=globalThis.fetch;
  globalThis.fetch=async(url,options={})=>{
    if((options.method==='POST')===(phase==='post')) return Response.json({retry_after:300},{status:429,headers:{'Retry-After':'240'}});
    return fetch(url,options);
  };
  const response=await request(f.e,r), value=await response.json();
  assert.equal(value.status,'retryable');
  assert(value.retry_after>=299 && value.retry_after<=300,JSON.stringify(value));
  const stored=await f.storage.get('report:'+r.id), before=f.calls.length;
  const restarted=new ReportStore(f.ctx,f.e);
  const retry=await send(restarted,r);
  assert.equal(retry.status,429);
  assert((await retry.json()).retry_after>=299);
  assert.equal((await f.storage.get('report:'+r.id)).attempts,stored.attempts);
  assert.equal(f.calls.length,before);
});

test('status lookup uses the same canonical UUID as submission', async () => {
  const f=fixture(),r=report();
  await request(f.e,r);
  const token=await sign({...user,kind:'session',csrf:'csrf-test',exp:Date.now()+60000},secret);
  const response=await worker.fetch(new Request(f.e.PUBLIC_ORIGIN+'/api/reports/'+r.id.toUpperCase(),{headers:{Cookie:`kfps_support=${token}`}}),f.e);
  assert.equal(response.status,200);
  assert.equal((await response.json()).status,'delivered');
});

test('retry after a failed retention alarm write repairs cleanup before delivery', async () => {
  const f=fixture(),r=report(),setAlarm=f.storage.setAlarm.bind(f.storage);
  f.storage.setAlarm=async()=>{throw new Error('synthetic alarm write failure');};
  assert.equal((await request(f.e,r)).status,503);
  assert.equal(f.calls.length,0);
  assert.equal(await f.storage.getAlarm(),null);
  f.storage.setAlarm=setAlarm;
  const restarted=new ReportStore(f.ctx,f.e);
  assert.equal((await (await send(restarted,r)).json()).status,'delivered');
  assert.equal(await f.storage.getAlarm(),(await f.storage.get('report:'+r.id)).created+30*86400000);
});

test('rate-limit headers and malformed bodies use safe bounded waits without leaking text', async () => {
  for (const [header,body,minimum,maximum] of [
    ['180','PRIVATE-NOT-JSON',179,180],
    [new Date(Date.now()+180000).toUTCString(),'{}',177,180],
    ['nonsense','{"retry_after":-1}',59,60],
    ['0','{"retry_after":"PRIVATE"}',59,60],
    ['0','x'.repeat(4097),59,60],
    ['999999999','{"retry_after":1e300}',86399,86400],
  ]) {
    const f=fixture(),r=report(),fetch=globalThis.fetch;
    globalThis.fetch=async(url,options={})=>options.method==='POST'
      ? new Response(body,{status:429,headers:{'Retry-After':header}}) : fetch(url,options);
    const response=await request(f.e,r),value=await response.json();
    assert.equal(value.status,'retryable');
    assert(value.retry_after>=minimum && value.retry_after<=maximum,JSON.stringify(value));
    assert.equal(JSON.stringify(value).includes('PRIVATE'),false);
  }
});

test('reading a delayed rate-limit body does not shorten the requested retry wait', async () => {
  const f=fixture(),r=report(),fetch=globalThis.fetch,now=Date.now;
  let clock=now();
  Date.now=()=>clock;
  try {
    globalThis.fetch=async(url,options={})=>{
      if(options.method!=='POST') return fetch(url,options);
      let part=0;
      return new Response(new ReadableStream({pull(controller) {
        if(part++===0) controller.enqueue(new TextEncoder().encode('{"retry_after":'));
        else { clock+=10000;controller.enqueue(new TextEncoder().encode('300}'));controller.close(); }
      }}),{status:429});
    };
    const value=await (await request(f.e,r)).json();
    assert.equal(value.status,'retryable');
    assert.equal(value.retry_after,300);
  } finally { Date.now=now; }
});

test('partial rate-limit retry after restart only sends the unfinished public destination', async () => {
  const f=fixture(),r=report(),fetch=globalThis.fetch;
  let limited=true,posts=0;
  globalThis.fetch=async(url,options={})=>{
    if(options.method==='POST') {
      posts++;
      if(String(url).includes('666666666666666666') && limited) return Response.json({retry_after:180},{status:429});
    }
    return fetch(url,options);
  };
  assert.equal((await (await request(f.e,r)).json()).status,'retryable');
  const restarted=new ReportStore(f.ctx,f.e);
  const waiting=await send(restarted,r);
  assert.equal(waiting.status,429);assert.equal(posts,2);
  const state=await f.storage.get('report:'+r.id);state.retryAt=0;await f.storage.put('report:'+r.id,state);
  limited=false;
  assert.equal((await (await send(restarted,r)).json()).status,'delivered');
  assert.equal(posts,3);
  assert.equal(f.calls.filter(c=>c.kind==='private'&&c.options.method==='POST').length,1);
});

test('failed acknowledgment persistence remains uncertain and never repeats an accepted post', async () => {
  const f=fixture(),r=report(),put=f.storage.put.bind(f.storage);
  let interrupted=false;
  f.storage.put=async(key,value)=>{
    if(key==='report:'+r.id && value.private.state==='sent' && !interrupted) {
      interrupted=true;throw new Error('synthetic receipt persistence interruption');
    }
    return put(key,value);
  };
  assert.equal((await request(f.e,r)).status,503);
  assert.equal((await f.storage.get('report:'+r.id)).private.state,'sending');
  const restarted=new ReportStore(f.ctx,f.e),before=f.calls.length;
  assert.equal((await (await send(restarted,r)).json()).status,'uncertain');
  assert.equal(f.calls.length,before);
  assert.equal(f.calls.filter(c=>c.options.method==='POST').length,1);
});

test('failing to persist sending state prevents any remote post and permits a safe retry', async () => {
  const f=fixture(),r=report(),put=f.storage.put.bind(f.storage);
  f.storage.put=async(key,value)=>{
    if(key==='report:'+r.id && value.private.state==='sending') throw new Error('synthetic state write failure');
    return put(key,value);
  };
  assert.equal((await request(f.e,r)).status,503);
  assert.equal(f.calls.filter(c=>c.options.method==='POST').length,0);
  f.storage.put=put;
  assert.equal((await (await send(new ReportStore(f.ctx,f.e),r)).json()).status,'delivered');
  assert.equal(f.calls.filter(c=>c.options.method==='POST').length,2);
});

test('post 5xx, redirects and malformed acknowledgments never cause automatic duplicate delivery', async () => {
  for(const [status,body,expected] of [[500,'PRIVATE-UPSTREAM','uncertain'],[302,'','blocked'],[200,'PRIVATE-BAD-ACK','uncertain'],[200,'{"id":"bad"}','uncertain']]) {
    const f=fixture(),r=report(),fetch=globalThis.fetch;let posts=0;
    globalThis.fetch=async(url,options={})=>{
      if(options.method==='POST') { posts++;return new Response(body,{status,headers:{Location:'https://unexpected.example/never-follow'}}); }
      return fetch(url,options);
    };
    const value=await (await request(f.e,r)).json();
    assert.equal(value.status,expected);assert.equal(JSON.stringify(value).includes('PRIVATE'),false);
    assert.equal((await (await send(new ReportStore(f.ctx,f.e),r)).json()).status,expected);
    assert.equal(posts,1);
    assert(f.calls.every(c=>c.options.redirect==='manual'));
  }
});

test('account-scoped status and receipt IDs do not reveal or deduplicate another account', async () => {
  const f=fixture(),r=report(),second='121212121212121212',other=new ReportStore({storage:new Storage()},f.e);
  f.e.REPORTS.get=id=>id===user.id?f.object:other;
  await request(f.e,r);
  const token=await sign({id:second,name:'Other synthetic account',kind:'session',csrf:'csrf-test',exp:Date.now()+60000},secret);
  const response=await worker.fetch(new Request(f.e.PUBLIC_ORIGIN+'/api/reports/'+r.id,{headers:{Cookie:`kfps_support=${token}`}}),f.e);
  assert.equal(response.status,404);
  const text=await response.text();assert.equal(text.includes(r.description),false);assert.equal(text.includes('public_url'),false);
  assert.equal((await (await request(f.e,r,{Cookie:`kfps_support=${token}`})).json()).status,'delivered');
  assert.equal(f.calls.filter(c=>c.options.method==='POST').length,4);
});

test('authenticated attachment failures enforce byte budgets and consent before creating receipts', async () => {
  const f=fixture(),{r,png}=await screenshotFixture();
  for(const metadata of [Array(4).fill(r.screenshots[0]),Array(3).fill({...r.screenshots[0],size:5*1024*1024}),[{...r.screenshots[0],size:5*1024*1024+1}]]) {
    assert.equal((await upload(f.e,{...r,screenshots:metadata},[png])).status,400);
  }
  const opts={'Content-Length':String(19*1024*1024)};
  assert.equal((await upload(f.e,r,[png],opts)).status,400);
  const expanded=new Blob([gzipSync('x'.repeat(24*1024*1024+1))],{type:'application/gzip'});
  const large=await request(f.e,report(),{},expanded);
  assert.equal(large.status,400);
  assert.equal((await large.json()).error,'Expanded private logs exceed the safety limit.');
  assert.equal((await request(f.e,{...report(),include_technical:false})).status,400);
  assert.equal(f.calls.length,0);
  assert.equal((await f.storage.list({prefix:'report:'})).size,0);
});

test('missing origin, missing CSRF, unsupported host and expired session fail before delivery', async () => {
  const f=fixture(),r=report();
  for(const extra of [{Origin:''},{'X-CSRF-Token':''},{Origin:'null'}]) assert.equal((await request(f.e,r,extra)).status,403);
  const token=await sign({...user,kind:'session',csrf:'csrf-test',exp:Date.now()-1},secret);
  assert.equal((await request(f.e,r,{Cookie:`kfps_support=${token}`})).status,401);
  assert.equal((await worker.fetch(new Request('https://unexpected.example/api/session'),f.e)).status,400);
  assert.equal(f.calls.length,0);
});
