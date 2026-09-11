import test, {afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {NUMBERS, BOOLS, ASSETS, ENUMS} from '../public/editor-diagnostics.mjs';
import worker, {ReportStore, sign, verify} from '../src/worker.mjs';
import {SCHEMA, normalizeReport, readJsonLimited, validWebhook, publicSummary, redact} from '../public/protocol.mjs';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const secret = 'test-only-not-a-real-secret-1234567890';
const user = {id: '111111111111111111', name: 'Synthetic Tester'};
const env = () => ({PUBLIC_ORIGIN: 'https://support.example', SESSION_SECRET: secret, DISCORD_CLIENT_ID: '222222222222222222', DISCORD_CLIENT_SECRET: 'test-client', DELIVERY_ENABLED: '1', DISCORD_GUILD_ID: '333333333333333333', SUPPORT_CHANNEL_ID: '444444444444444444', PRIVATE_CHANNEL_ID: '555555555555555555', PUBLIC_WEBHOOK_URL: 'https://discord.com/api/webhooks/666666666666666666/' + 'a'.repeat(40), PRIVATE_WEBHOOK_URL: 'https://discord.com/api/webhooks/777777777777777777/' + 'b'.repeat(40), DISCORD_JOIN_URL: 'https://discord.com/channels/333333333333333333/444444444444444444'});
const report = () => normalizeReport({schema: SCHEMA, id: crypto.randomUUID(), created_at: '2026-09-06T12:00:00Z', feature: 'Editor', title: 'Synthetic test', description: 'Dragging shapes becomes slow.', technical: {app: {version: '3.1.60'}, hardware: {gpus: [{name: 'Synthetic GPU'}]}}});
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
async function request(e, data, extra = {}) {
  const token = await sign({...user, kind:'session', csrf:'csrf-test', exp:Date.now()+60000}, secret);
  return worker.fetch(new Request(e.PUBLIC_ORIGIN + '/api/reports', {method:'POST', headers:{'Content-Type':'application/json', Origin:e.PUBLIC_ORIGIN, Cookie:`kfps_support=${token}`, 'X-CSRF-Token':'csrf-test', ...extra}, body:JSON.stringify(data)}),e);
}
const send = (object, r) => object.fetch(new Request('https://report.internal/send', {method:'POST', body:JSON.stringify({report:r,user})}));

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

test('real Python disk-log report survives review and private attachment, never public post', async () => {
  const root = fileURLToPath(new URL('../../../', import.meta.url));
  const code = `import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, 'KFPS.UI/src')
from kfps_ui.support_report import build_support_report
from tools.fabric_editor_diagnostics import EditorDiagnostics
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory)
 runtime=root/'runtime/fabric-editor'
 runtime.mkdir(parents=True)
 (runtime/'desktop.log').write_text('Error: GPU reset\\nsession_token=DO_NOT_SEND\\ndata:image/png;base64,AAAA\\n')
 logger=EditorDiagnostics(root, runtime)
 logger.accept({'schema':1,'page':'a'*32,'seq':1,'metrics':{'frameMax':280},'state':{'layers':355,'editorRevision':2026091101},'events':[{'kind':'long-task','duration':280,'action':'rotate','message':'DO_NOT_SEND'}]})
 logger.close()
 report=build_support_report(root, {'page':'editor','log':'Synthetic app error','services':{'editor':{'lastError':'Dragging shapes becomes slow.'}}}, since=time.time()-20, collect=lambda:{})
 print(json.dumps(report))`;
  const raw = JSON.parse(execFileSync(process.platform === 'win32' ? 'py' : 'python3', [...(process.platform === 'win32' ? ['-3.12'] : []), '-c', code], {cwd: root, encoding: 'utf8'}));
  raw.technical.logs.push(...Array.from({length: 8}, (_, i) => ({source: `worker-${i}`, text: `Error: worker ${i} failed`, age_seconds: 25, previous_session: true})));
  const reviewed = normalizeReport(raw);
  assert.deepEqual(normalizeReport(reviewed), reviewed);
  assert.equal(reviewed.technical.logs.length, 10);
  assert.equal(reviewed.technical.editor.page.metrics.frameMax, 280);
  assert.equal(reviewed.technical.editor.page.state.layers, 355);
  assert.equal(reviewed.technical.editor.recent[0].action, 'rotate');
  assert.equal(JSON.stringify(reviewed).includes('DO_NOT_SEND'), false);
  const f = fixture();
  assert.equal((await (await request(f.e, reviewed)).json()).status, 'delivered');
  const posts = f.calls.filter(c => c.options.method === 'POST');
  const attachment = JSON.parse(await posts[0].options.body.get('files[0]').text());
  assert.deepEqual(attachment.technical.editor, reviewed.technical.editor);
  assert.deepEqual(attachment.technical.logs, reviewed.technical.logs);
  assert.equal(posts[1].options.body.includes('GPU reset'), false);
  assert.equal(posts[1].options.body.includes('worker-7'), false);
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
