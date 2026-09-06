import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const require = createRequire(new URL('../../community_worker/package.json', import.meta.url));
const {Miniflare, convertV4MiniflareOptions} = require('miniflare');
const {build} = require('esbuild');
const config = JSON.parse(await readFile(new URL('../wrangler.jsonc', import.meta.url), 'utf8'));
const bundle = await build({entryPoints:[fileURLToPath(new URL('../src/worker.mjs', import.meta.url))], bundle:true, write:false, format:'esm', platform:'browser'});

test('actual workerd OAuth and SQLite delivery survive duplicate submission and redirect refusal', async () => {
  const origin='https://support.example', calls=[];
  let redirectToken=false;
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
    } else {
      const body=await request.json(); assert.ok(body.thread_name); assert.equal(body.content.includes('Synthetic GPU'),false);
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
    const report={schema:'kfps-support-report/1',id:crypto.randomUUID(),created_at:new Date().toISOString(),feature:'Editor',title:'Runtime test',description:'Synthetic runtime test only',technical:{hardware:{gpus:[{name:'Synthetic GPU'}]}}};
    const submit=()=>mf.dispatchFetch(origin+'/api/reports',{method:'POST',headers:{Cookie:cookie,Origin:origin,'X-CSRF-Token':session.csrf,'Content-Type':'application/json'},body:JSON.stringify(report)});
    assert.equal((await(await submit()).json()).status,'delivered');
    assert.equal((await(await submit()).json()).status,'delivered');
    assert.equal(calls.filter(c=>c.method==='POST'&&c.path.includes('/webhooks/')).length,2);
    await mf.setOptions(options);
    assert.equal((await(await mf.dispatchFetch(origin+'/api/reports/'+report.id,{headers:{Cookie:cookie}})).json()).status,'delivered');
    assert.equal((await(await submit()).json()).status,'delivered');
    assert.equal(calls.filter(c=>c.method==='POST'&&c.path.includes('/webhooks/')).length,2);
    redirectToken=true; const before=calls.length;
    const refused=await login();
    assert.equal(refused.headers.get('location'),origin+'/?auth=failed&detail=token-request-302');
    assert.equal(calls.length,before+1);
  } finally {await mf.dispose();}
});
