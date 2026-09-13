const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

(async()=>{
  const output=path.resolve(process.argv[2]);fs.mkdirSync(output,{recursive:true});
  const {default:worker,ReportStore,sign}=await import(pathToFileURL(path.join(__dirname,'../src/worker.mjs')));
  const publicRoot=path.join(__dirname,'../public'),allowed=new Set(fs.readdirSync(publicRoot));
  const env={SESSION_SECRET:'synthetic-browser-test-secret-123456789',DISCORD_CLIENT_ID:'111111111111111111',DISCORD_CLIENT_SECRET:'synthetic',DELIVERY_ENABLED:'1',DISCORD_JOIN_URL:'https://discord.gg/XT8dG8bDKy',PUBLIC_WEBHOOK_URL:'https://discord.com/api/webhooks/222222222222222222/'+'a'.repeat(40),PRIVATE_WEBHOOK_URL:'https://discord.com/api/webhooks/333333333333333333/'+'b'.repeat(40)};
  const objects=new Map(),errors=[],requests=[],checks=[];
  let caseIP='192.0.2.2';
  env.REPORTS={idFromName:id=>id,get:id=>{
    if(!objects.has(id)){
      const values=new Map();const storage={get:async k=>structuredClone(values.get(k)),put:async(k,v)=>values.set(k,structuredClone(v)),setAlarm:async()=>{},delete:async k=>values.delete(k)};
      objects.set(id,new ReportStore({storage},env));
    }return objects.get(id);
  }};
  env.ASSETS={fetch:async request=>{
    let name=new URL(request.url).pathname.slice(1)||'index.html';
    if(!allowed.has(name)&&allowed.has(name+'.html'))name+='.html';
    if(!allowed.has(name))return new Response('Not found',{status:404});
    return new Response(fs.readFileSync(path.join(publicRoot,name)),{headers:{'Content-Type':name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':name.endsWith('.png')?'image/png':'text/javascript'}});
  }};
  const server=http.createServer(async(req,res)=>{
    try{
      requests.push(req.url);
      if(req.url.startsWith('/api/reports'))throw Error('Unexpected report submission');
      const parts=[];for await(const part of req)parts.push(part);
      const headers={...req.headers,'cf-connecting-ip':caseIP};
      const response=await worker.fetch(new Request(env.PUBLIC_ORIGIN+req.url,{method:req.method,headers,...(['GET','HEAD'].includes(req.method)?{}:{body:Buffer.concat(parts)})}),env);
      const resultHeaders=Object.fromEntries(response.headers);
      const cookies=response.headers.getSetCookie();if(cookies.length)resultHeaders['set-cookie']=cookies;
      res.writeHead(response.status,resultHeaders);res.end(Buffer.from(await response.arrayBuffer()));
    }catch(error){errors.push(String(error));res.writeHead(500);res.end('Fixture error');}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));env.PUBLIC_ORIGIN=`http://127.0.0.1:${server.address().port}`;
  const check=(ok,name)=>{assert.ok(ok,name);checks.push(name);};
  let browser;
  try{
    browser=await chromium.launch({channel:'chrome',headless:true});
    let caseNumber=2;
    for(const locale of ['en-US','ko-KR']) for(const mode of ['blocked','silent','no-host']){
      caseIP=`192.0.2.${caseNumber++}`;
      const app=await browser.newContext({locale,viewport:{width:1080,height:840}}),system=await browser.newContext({locale,viewport:{width:1100,height:900}});
      await app.addInitScript(()=>Object.defineProperty(window,'KFPSNativeReport',{value:true}));
      await app.addInitScript(offset=>{const original=Date.now;Date.now=()=>original()+offset;},mode==='blocked'?-2000:mode==='silent'?86400000:-86400000);
      const token=await sign({kind:'session',id:'444444444444444444',name:'Synthetic Browser User',csrf:'browser-csrf',exp:Date.now()+3600000},env.SESSION_SECRET);
      await system.addCookies([{name:'kfps_support',value:token,url:env.PUBLIC_ORIGIN,httpOnly:true,sameSite:'Lax'}]);
      const report=await app.newPage(),approval=await system.newPage();
      for(const page of [report,approval])page.on('pageerror',e=>errors.push(String(e)));
      await report.goto(env.PUBLIC_ORIGIN);await report.locator('#login').waitFor();
      await report.locator('#description').fill('My edited description stays in KFPS.');
      if(mode==='blocked') {
        await report.route('**/api/native-auth/start',route=>route.fulfill({status:429,contentType:'application/json',body:JSON.stringify({error:'Synthetic rate limit'})}));
        await report.locator('#login').click();
        await report.waitForFunction(()=>document.getElementById('notice').textContent.includes(document.documentElement.lang==='ko'?'너무 여러 번':'Too many'));
        check(await report.locator('#login').isEnabled(),`${locale}: rate-limited attempt can retry`);
        check(await report.evaluate(()=>window.KFPSReportSignIn.diagnostics().some(e=>e.result==='rate-limited'&&e.http_status===429)),`${locale}: rate-limit reason reaches diagnostics`);
        await report.unroute('**/api/native-auth/start');
      }
      await report.locator('#login').click();
      await report.locator('#native-signin').waitFor({state:'visible'});
      const url=await report.locator('#native-link').inputValue(),launch={url,id:new URL(url).searchParams.get('ticket')};
      if(mode!=='no-host')await report.evaluate(({launch,mode})=>window.KFPSReportSignIn.opened(launch.id,mode==='silent'),{launch,mode});
      check(await report.locator('#native-reopen').getAttribute('href')===url,`${locale}/${mode}: fallback keeps the pending ticket`);
      await report.locator('#report-language').selectOption(locale==='ko-KR'?'en':'ko');
      check(await report.locator('#native-reopen').getAttribute('href')===url,`${locale}/${mode}: language switch preserves pending approval`);
      await report.locator('#report-language').selectOption('auto');
      check(await report.locator('#native-reopen').innerText()===(locale==='ko-KR'?'기본 브라우저에서 열기':'Open in default browser'),`${locale}/${mode}: fallback label is localized`);
      check(await report.locator('#saved-report-recovery').isHidden(),`${locale}/${mode}: native review never asks for a log file`);
      check(await report.locator('#private-logs-section').evaluate(e=>!e.closest('details')&&!e.hidden),`${locale}/${mode}: automatic logs explanation is expanded`);
      check(await report.locator('#report-privacy').getAttribute('lang')===(locale==='ko-KR'?'ko':'en'),`${locale}/${mode}: privacy language matches browser locale`);
      check((await report.locator('#report-privacy').innerText()).includes('Hestia Cummings <hestia.cummings@yandex.com>'),`${locale}/${mode}: operator and deletion contact are visible`);
      check(await report.locator('#send').isDisabled(),`${locale}/${mode}: sign-in cannot silently enable a checked report without logs`);
      await report.locator('#native-link').click();
      check(await report.locator('#native-link').evaluate(e=>e.readOnly&&e.selectionStart===0&&e.selectionEnd===e.value.length),`${locale}/${mode}: backup URL is read-only and selectable`);
      if(mode==='blocked')for(const width of [1080,520,390]){
        await report.setViewportSize({width,height:840});
        check(await report.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${locale}: report fallback has no overflow at ${width}`);
        await report.screenshot({path:path.join(output,`report-fallback-${locale}-${width}.png`),fullPage:true});
        await report.locator('#private-logs-section').evaluate(e=>e.scrollIntoView({block:'start'}));
        await report.screenshot({path:path.join(output,`automatic-logs-${locale}-${width}.png`)});
        await report.locator('#report-privacy').evaluate(e=>e.scrollIntoView({block:'start'}));
        await report.screenshot({path:path.join(output,`privacy-${locale}-${width}.png`)});
      }
      await report.setViewportSize({width:1080,height:840});
      // Capture the actual target=_blank navigation without sending this fixture
      // to Discord. Native Qt separately tests interception into the OS browser.
      await app.route('**/auth/native?ticket=*',route=>route.fulfill({contentType:'text/html',body:'External browser handoff fixture'}));
      const opened=app.waitForEvent('page');await report.locator('#native-reopen').click();
      const popup=await opened;await popup.waitForURL(url);await popup.close();
      check(await report.evaluate(()=>window.KFPSReportSignIn.request())===null,`${locale}/${mode}: manual tab suppresses duplicate automatic launch`);
      const code=await report.locator('#native-signin-code').innerText();
      if(mode==='blocked'){
        await approval.route('**/api/native-auth/approval?ticket=*',route=>route.abort('failed'));
        await approval.goto(launch.url);
        await approval.waitForFunction(()=>/Failed to fetch|연결/.test(document.getElementById('auth-info').textContent));
        check((await approval.locator('#auth-info').innerText()).includes(locale==='ko-KR'?'연결':'Failed to fetch'),`${locale}: approval connection error is localized`);
        await approval.unroute('**/api/native-auth/approval?ticket=*');
      }
      await approval.goto(launch.url);await approval.locator('#approval').waitFor({state:'visible'});
      check(await approval.locator('#approval-code').innerText()===code,`${locale}: the code matches across isolated app/browser sessions`);
      check(await approval.locator('#approve').isDisabled(),`${locale}: approval needs explicit confirmation`);
      if(mode==='blocked'){
        await approval.locator('#report-language').selectOption(locale==='ko-KR'?'en':'ko');
        await approval.locator('#approval').waitFor({state:'visible'});
        check(await approval.locator('#approval-code').innerText()===code&&await approval.locator('#approve').isDisabled(),`${locale}: approval language switch retains ticket without authorizing`);
        await approval.locator('#report-language').selectOption('auto');await approval.locator('#approval').waitFor({state:'visible'});
      }
      for(const width of [1100,390]){
        await approval.setViewportSize({width,height:900});
        check(await approval.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${locale}: approval has no overflow at ${width}`);
        if(mode==='blocked')await approval.screenshot({path:path.join(output,`approval-${locale}-${width}.png`),fullPage:true});
      }
      if(mode==='blocked')await report.screenshot({path:path.join(output,`report-waiting-${locale}.png`),fullPage:true});
      await approval.locator('#match-code').check();
      if(mode==='blocked'){
        await approval.route('**/api/native-auth/approve',route=>route.abort('failed'));
        await approval.locator('#approve').click();
        await approval.waitForFunction(()=>/Failed to fetch|연결/.test(document.getElementById('notice').textContent));
        check(await approval.locator('#approve').isEnabled()&&await report.locator('#native-signin').isVisible(),`${locale}: failed approval can retry and leaves report waiting`);
        await approval.unroute('**/api/native-auth/approve');
      }
      await approval.locator('#approve').click();
      await report.locator('#identity').filter({hasText:'Synthetic Browser User'}).waitFor();
      check(await approval.locator('#notice').innerText()==='',`${locale}/${mode}: successful approval clears stale errors`);
      check(await report.locator('#send').isDisabled(),`${locale}/${mode}: completed sign-in still requires checked logs`);
      check(await report.locator('#native-signin').isHidden() && await report.locator('#native-link').inputValue()==='' && await report.locator('#native-reopen').getAttribute('href')===null,`${locale}/${mode}: signed-in form clears approval links`);
      check(await report.locator('#description').inputValue()==='My edited description stays in KFPS.',`${locale}: browser authorization preserves report text`);
      check(await report.evaluate(()=>window.KFPSReportSignIn.diagnostics().some(e=>e.stage==='session'&&e.result==='authenticated')),`${locale}/${mode}: clock-skewed form records successful authentication`);
      check(report.url()===env.PUBLIC_ORIGIN+'/',`${locale}: the native report never navigates to Discord`);
      await report.reload();await report.locator('#identity').filter({hasText:'Synthetic Browser User'}).waitFor();
      await report.close();const reopened=await app.newPage();await reopened.goto(env.PUBLIC_ORIGIN);
      await reopened.locator('#identity').filter({hasText:'Synthetic Browser User'}).waitFor();
      check(await reopened.locator('#description').inputValue()==='My edited description stays in KFPS.',`${locale}: closing and reopening preserves the edited draft`);
      await reopened.locator('#logout').click();await reopened.locator('#login').waitFor({state:'visible'});
      await reopened.locator('#login').click();await reopened.waitForFunction(()=>!!window.KFPSReportSignIn.request());
      const cancelled=await reopened.evaluate(()=>window.KFPSReportSignIn.request());
      await approval.goto(cancelled.url);await approval.locator('#approval').waitFor({state:'visible'});
      await approval.locator('#deny').click();await reopened.locator('#native-signin').waitFor({state:'hidden'});
      check(await reopened.locator('#login').isVisible(),`${locale}: cancelling browser approval leaves the report usable`);
      check(await reopened.locator('#native-link').inputValue()==='',`${locale}/${mode}: denied sign-in clears manual link`);
      check((await reopened.locator('#notice').innerText()).includes(locale==='ko-KR'?'거절':'declined'),`${locale}/${mode}: browser denial has a specific explanation`);
      await app.close();await system.close();
    }
    check(!requests.some(v=>v.startsWith('/api/reports')),'authorization never submits reports or logs');
    assert.deepEqual(errors,[]);checks.push('no page or fixture errors');
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,checks,realDiscordPosts:0},null,2));
    console.log(JSON.stringify({passed:true,checks}));
  }catch(error){fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:false,checks,error:String(error),errors},null,2));throw error;}
  finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
