import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {describeScreenshot} from '../public/screenshots.mjs';
import {normalizeReport} from '../public/protocol.mjs';
import {submissionBody} from '../src/submission.mjs';
import {gzipSync} from 'node:zlib';
import {describePrivateLogs,APP_LOG_SCHEMA} from '../public/private-logs.mjs';
import {redact} from '../public/protocol.mjs';

const require = createRequire(new URL('../../community_worker/package.json', import.meta.url));
const {Miniflare, convertV4MiniflareOptions} = require('miniflare');
const {build} = require('esbuild');
const config = JSON.parse(await readFile(new URL('../wrangler.jsonc', import.meta.url), 'utf8'));
const bundle = await build({entryPoints:[fileURLToPath(new URL('../src/worker.mjs', import.meta.url))], bundle:true, write:false, format:'esm', platform:'browser'});

test('actual workerd OAuth and SQLite delivery survive duplicate submission and redirect refusal', async () => {
  const origin='https://support.example', calls=[];
  const editor={schema:'kfps-editor-diagnostics/1',editor_runtime:{status:'verified',qt:'6.11.1',chromium:'140.0.7339.225'},
    recent:[{kind:'commit',action:'rotate',documentId:1,commandId:2,commitId:3},
      {kind:'checkpoint',state:'saved',documentId:1,commandId:2,commitId:3}],
    page:{page:'a'.repeat(32),seq:1,metrics:{frameMax:280},state:{layers:2401,cachePixels:9000,queueDepth:2}}};
  const logs=Array.from({length:16},(_,i)=>({source:`worker-${i}`,text:`Synthetic private log ${i}`}));
  let redirectToken=false;
  const png=new Blob([Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aipkAAAAASUVORK5CYII=','base64')],{type:'image/png'});
  let screenshotPosts=0;
  let privateLogPosts=0;
  const retainedLine=JSON.stringify({schema:'kfps-editor-diagnostics/1',session:'a'.repeat(32),utc:new Date().toISOString(),serial:1,kind:'commit',action:'move',commitId:1})+'\n';
  const fullRetained=['performance.2.jsonl','performance.1.jsonl','performance.jsonl','desktop.log.2','desktop.log.1','desktop.log','transfer-worker-0001.log','generator-worker-0002.log'].map(name=>{
    const line=name.startsWith('performance')?retainedLine:'Editor runtime started normally\n';
    const text=line.repeat(Math.floor(2*1024*1024/Buffer.byteLength(line)));
    return {name,modified_utc:new Date().toISOString(),source_bytes:Buffer.byteLength(text),omitted_lines:0,text};
  });
  const privateLogs=new Blob([gzipSync(JSON.stringify({schema:APP_LOG_SCHEMA,created_at:new Date().toISOString(),files:fullRetained,warnings:[]}))],{type:'application/gzip'});
  const bindings={...config.vars, PUBLIC_ORIGIN:origin, DISCORD_CLIENT_ID:'222222222222222222', DISCORD_CLIENT_SECRET:'synthetic-client-secret', SESSION_SECRET:'synthetic-session-signing-secret-12345678', DELIVERY_ENABLED:'1', DISCORD_GUILD_ID:'333333333333333333', SUPPORT_CHANNEL_ID:'444444444444444444', PRIVATE_CHANNEL_ID:'555555555555555555', PUBLIC_WEBHOOK_URL:'https://discord.com/api/webhooks/666666666666666666/'+'a'.repeat(40), PRIVATE_WEBHOOK_URL:'https://discord.com/api/webhooks/777777777777777777/'+'b'.repeat(40)};
  const options=convertV4MiniflareOptions({modules:true,script:bundle.outputFiles[0].text,compatibilityDate:config.compatibility_date,bindings,durableObjects:{REPORTS:{className:'ReportStore',useSQLite:true}},outboundService:async request=>{
    const url=new URL(request.url); calls.push({path:url.pathname,method:request.method});
    if(url.pathname==='/api/v10/oauth2/token') {
      assert.equal(request.method,'POST');
      if(redirectToken) return new Response(null,{status:302,headers:{Location:'https://unexpected.example/never-follow'}});
      const form=await request.formData(); assert.equal(form.get('redirect_uri'),origin+'/auth/callback');
      return Response.json({access_token:'synthetic-oauth-token',token_type:'Bearer',scope:'identify'});
    }
    if(url.pathname==='/api/v10/users/@me') return Response.json({id:'111111111111111111',username:'synthetic-tester'});
    assert.equal(url.hostname,'discord.com');
    const privateChannel=url.pathname.includes('777777777777777777');
    if(request.method==='GET') return Response.json({type:1,guild_id:bindings.DISCORD_GUILD_ID,channel_id:privateChannel?bindings.PRIVATE_CHANNEL_ID:bindings.SUPPORT_CHANNEL_ID});
    assert.equal(url.searchParams.get('wait'),'true');
    if(privateChannel) {
      const body=await request.formData(), attachment=JSON.parse(await body.get('files[0]').text());
      assert.equal(attachment.technical.hardware.gpus[0].name,'Synthetic GPU');
      assert.deepEqual(attachment.technical.editor.editor_runtime,editor.editor_runtime);
      assert.deepEqual(attachment.technical.editor.recent,editor.recent);
      assert.equal(attachment.technical.editor.page.state.cachePixels,9000);
      assert.deepEqual(attachment.technical.logs,logs);
      if(attachment.private_logs) {
        assert.deepEqual(Buffer.from(await body.get('files[1]').arrayBuffer()),Buffer.from(await privateLogs.arrayBuffer()));
        const payload=JSON.parse(body.get('payload_json'));
        assert.equal(payload.attachments[1].filename,`kfps-app-logs-${attachment.id}.json.gz`);
        assert.equal(body.get('files[1]').name,payload.attachments[1].filename);privateLogPosts++;
      }
    } else {
      let body;
      if(request.headers.get('content-type').startsWith('multipart/form-data')) {
        const form=await request.formData();body=JSON.parse(form.get('payload_json'));
        assert.deepEqual(Buffer.from(await form.get('files[0]').arrayBuffer()),Buffer.from(await png.arrayBuffer()));
        assert.equal(body.attachments[0].filename,'screenshot-1.png');screenshotPosts++;
      } else body=await request.json();
      assert.ok(body.thread_name); assert.equal(body.content.includes('Synthetic GPU'),false);
      for(const privateField of ['chromium','commandId','cachePixels','Synthetic private log','desktop.log','retained','private_logs']) assert.equal(body.content.includes(privateField),false);
    }
    return Response.json({id:'888888888888888888',channel_id:privateChannel?bindings.PRIVATE_CHANNEL_ID:'999999999999999999'});
  }});
  const mf=new Miniflare(options);
  try {
    async function login() {
      const start=await mf.dispatchFetch(origin+'/auth/start',{redirect:'manual'});
      assert.equal(start.status,303,await start.text());
      const state=new URL(start.headers.get('location')).searchParams.get('state');
      const cookie=start.headers.get('set-cookie').split(';')[0];
      return mf.dispatchFetch(origin+'/auth/callback?state='+state+'&code=synthetic-code',{headers:{Cookie:cookie},redirect:'manual'});
    }
    const callback=await login(); assert.equal(callback.headers.get('location'),origin+'/');
    const cookie='kfps_support='+callback.headers.get('set-cookie').match(/kfps_support=([^;]+)/)[1];
    const session=await(await mf.dispatchFetch(origin+'/api/session',{headers:{Cookie:cookie}})).json();
    assert.equal(session.authenticated,true);
    const nativePost=(path,cookie,body={},csrf='')=>mf.dispatchFetch(origin+path,{method:'POST',headers:{Cookie:cookie,Origin:origin,'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});
    const nativeStart=await nativePost('/api/native-auth/start','');
    assert.equal(nativeStart.status,200,await nativeStart.clone().text());
    const nativeRequest=await nativeStart.json(), pending=nativeStart.headers.get('set-cookie').split(';')[0];
    const nativeOauth=await mf.dispatchFetch(origin+'/auth/start?native='+nativeRequest.id,{redirect:'manual'});
    const nativeState=new URL(nativeOauth.headers.get('location')).searchParams.get('state');
    const nativeCallback=await mf.dispatchFetch(origin+'/auth/callback?state='+nativeState+'&code=synthetic-code',{headers:{Cookie:nativeOauth.headers.get('set-cookie').split(';')[0]},redirect:'manual'});
    assert.equal(nativeCallback.headers.get('location'),nativeRequest.url);
    const browserCookie='kfps_support='+nativeCallback.headers.get('set-cookie').match(/kfps_support=([^;]+)/)[1];
    const approval=await(await mf.dispatchFetch(origin+'/api/native-auth/approval?ticket='+nativeRequest.id,{headers:{Cookie:browserCookie}})).json();
    assert.equal(approval.code,nativeRequest.code);
    assert.equal((await nativePost('/api/native-auth/approve',browserCookie,{ticket:nativeRequest.id,code:approval.code,confirm:true},approval.csrf)).status,200);
    await mf.setOptions(options);
    const nativeReady=await nativePost('/api/native-auth/poll',pending);
    assert.deepEqual(await nativeReady.clone().json(),{status:'ready'});
    const nativeCookie=nativeReady.headers.get('set-cookie').split(';')[0];
    const nativeSession=await(await mf.dispatchFetch(origin+'/api/session',{headers:{Cookie:nativeCookie}})).json();
    assert.equal(nativeSession.authenticated,true);
    assert.notEqual(nativeSession.csrf,approval.csrf,'native and default-browser sessions are distinct');
    assert.equal(calls.filter(c=>c.path.includes('/webhooks/')).length,0,'authorization never sends logs or a report');
    assert.equal((await nativePost('/api/native-auth/poll',pending)).headers.get('set-cookie'),nativeReady.headers.get('set-cookie'),'workerd restart and retries preserve pending authorization');
    const report={schema:'kfps-support-report/1',id:crypto.randomUUID(),created_at:new Date().toISOString(),feature:'Editor',title:'Runtime test',description:'Synthetic runtime test only',technical:{hardware:{gpus:[{name:'Synthetic GPU'}]},editor,logs},private_logs:(await describePrivateLogs(privateLogs,{redact})).metadata};
    const missing=await mf.dispatchFetch(origin+'/api/reports',{method:'POST',headers:{Cookie:cookie,Origin:origin,'X-CSRF-Token':session.csrf,'Content-Type':'application/json'},body:JSON.stringify({...report,private_logs:undefined})});
    assert.equal(missing.status,400);assert.equal(calls.filter(c=>c.path.includes('/webhooks/')).length,0);
    const submit=async()=>{
      const wire=new Request(origin+'/api/reports',{method:'POST',headers:{Cookie:cookie,Origin:origin,'X-CSRF-Token':session.csrf},body:submissionBody(report,[],privateLogs)});
      return mf.dispatchFetch(wire.url,{method:'POST',headers:Object.fromEntries(wire.headers),body:await wire.arrayBuffer()});
    };
    assert.equal((await(await submit()).json()).status,'delivered');
    assert.equal((await(await submit()).json()).status,'delivered');
    assert.equal(calls.filter(c=>c.method==='POST'&&c.path.includes('/webhooks/')).length,2);
    await mf.setOptions(options);
    assert.equal((await(await mf.dispatchFetch(origin+'/api/reports/'+report.id,{headers:{Cookie:cookie}})).json()).status,'delivered');
    assert.equal((await(await submit()).json()).status,'delivered');
    assert.equal(calls.filter(c=>c.method==='POST'&&c.path.includes('/webhooks/')).length,2);
    const withImage=normalizeReport({...report,id:crypto.randomUUID(),screenshots:[await describeScreenshot(png)],screenshots_public:true});
    const upload=async()=>{
      // Serialize browser-style multipart bytes across Node/Miniflare's separate FormData implementations.
      const wire=new Request(origin+'/api/reports',{method:'POST',headers:{Cookie:cookie,Origin:origin,'X-CSRF-Token':session.csrf},body:submissionBody(withImage,[png],privateLogs)});
      return mf.dispatchFetch(wire.url,{method:'POST',headers:Object.fromEntries(wire.headers),body:await wire.arrayBuffer()});
    };
    const uploaded=await(await upload()).json();assert.equal(uploaded.status,'delivered',JSON.stringify(uploaded));
    assert.equal((await(await upload()).json()).status,'delivered');
    assert.equal(screenshotPosts,1);
    assert.equal(calls.filter(c=>c.method==='POST'&&c.path.includes('/webhooks/')).length,4);
    const withLogs=normalizeReport({...report,id:crypto.randomUUID(),private_logs:(await describePrivateLogs(privateLogs,{redact})).metadata});
    const uploadLogs=async()=>{
      const wire=new Request(origin+'/api/reports',{method:'POST',headers:{Cookie:cookie,Origin:origin,'X-CSRF-Token':session.csrf},body:submissionBody(withLogs,[],privateLogs)});
      return mf.dispatchFetch(wire.url,{method:'POST',headers:Object.fromEntries(wire.headers),body:await wire.arrayBuffer()});
    };
    const deliveredLogs=await(await uploadLogs()).json();assert.equal(deliveredLogs.status,'delivered',JSON.stringify(deliveredLogs));
    assert.equal((await(await uploadLogs()).json()).status,'delivered');assert.equal(privateLogPosts,3);
    assert.equal(calls.filter(c=>c.method==='POST'&&c.path.includes('/webhooks/')).length,6);
    redirectToken=true; const before=calls.length;
    const refused=await login();
    assert.equal(refused.headers.get('location'),origin+'/?auth=failed&detail=token-request-302');
    assert.equal(calls.length,before+1);
  } finally {await mf.dispose();}
});
