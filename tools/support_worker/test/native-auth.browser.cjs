const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

(async()=>{
  const output=path.resolve(process.argv[2]);fs.mkdirSync(output,{recursive:true});
  const {default:worker,ReportStore,sign}=await import(pathToFileURL(path.join(__dirname,'../src/worker.mjs')));
  const publicRoot=path.join(__dirname,'../public'),allowed=new Set(fs.readdirSync(publicRoot));
  const env={SESSION_SECRET:'synthetic-browser-test-secret-123456789',DISCORD_CLIENT_ID:'111111111111111111',DISCORD_CLIENT_SECRET:'synthetic',DELIVERY_ENABLED:'1',DISCORD_JOIN_URL:'https://discord.gg/XT8dG8bDKy',PUBLIC_WEBHOOK_URL:'https://discord.com/api/webhooks/222222222222222222/'+'a'.repeat(40),PRIVATE_WEBHOOK_URL:'https://discord.com/api/webhooks/333333333333333333/'+'b'.repeat(40)};
  const objects=new Map(),errors=[],requests=[],checks=[];
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
      const headers={...req.headers,'cf-connecting-ip':'192.0.2.2'};
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
    for(const locale of ['en-US','ko-KR']){
      const app=await browser.newContext({locale,viewport:{width:1080,height:840}}),system=await browser.newContext({locale,viewport:{width:1100,height:900}});
      await app.addInitScript(()=>Object.defineProperty(window,'KFPSNativeReport',{value:true}));
      const token=await sign({kind:'session',id:'444444444444444444',name:'Synthetic Browser User',csrf:'browser-csrf',exp:Date.now()+3600000},env.SESSION_SECRET);
      await system.addCookies([{name:'kfps_support',value:token,url:env.PUBLIC_ORIGIN,httpOnly:true,sameSite:'Lax'}]);
      const report=await app.newPage(),approval=await system.newPage();
      for(const page of [report,approval])page.on('pageerror',e=>errors.push(String(e)));
      await report.goto(env.PUBLIC_ORIGIN);await report.locator('#login').waitFor();
      await report.locator('#description').fill('My edited description stays in KFPS.');
      await report.locator('#login').click();
      await report.waitForFunction(()=>!!window.KFPSReportSignIn.request());
      const launch=await report.evaluate(()=>window.KFPSReportSignIn.request());
      await report.evaluate(value=>window.KFPSReportSignIn.opened(value.id,true),launch);
      const code=await report.locator('#native-signin-code').innerText();
      await approval.goto(launch.url);await approval.locator('#approval').waitFor({state:'visible'});
      check(await approval.locator('#approval-code').innerText()===code,`${locale}: the code matches across isolated app/browser sessions`);
      check(await approval.locator('#approve').isDisabled(),`${locale}: approval needs explicit confirmation`);
      for(const width of [1100,390]){
        await approval.setViewportSize({width,height:900});
        check(await approval.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${locale}: approval has no overflow at ${width}`);
        await approval.screenshot({path:path.join(output,`approval-${locale}-${width}.png`),fullPage:true});
      }
      await report.screenshot({path:path.join(output,`report-waiting-${locale}.png`),fullPage:true});
      await approval.locator('#match-code').check();await approval.locator('#approve').click();
      await report.getByText('Signed in as Synthetic Browser User',{exact:true}).waitFor();
      check(await report.locator('#description').inputValue()==='My edited description stays in KFPS.',`${locale}: browser authorization preserves report text`);
      check(report.url()===env.PUBLIC_ORIGIN+'/',`${locale}: the native report never navigates to Discord`);
      await report.reload();await report.getByText('Signed in as Synthetic Browser User',{exact:true}).waitFor();
      await report.close();const reopened=await app.newPage();await reopened.goto(env.PUBLIC_ORIGIN);
      await reopened.getByText('Signed in as Synthetic Browser User',{exact:true}).waitFor();
      check(await reopened.locator('#description').inputValue()==='My edited description stays in KFPS.',`${locale}: closing and reopening preserves the edited draft`);
      await reopened.locator('#logout').click();await reopened.locator('#login').waitFor({state:'visible'});
      await reopened.locator('#login').click();await reopened.waitForFunction(()=>!!window.KFPSReportSignIn.request());
      const cancelled=await reopened.evaluate(()=>window.KFPSReportSignIn.request());
      await approval.goto(cancelled.url);await approval.locator('#approval').waitFor({state:'visible'});
      await approval.locator('#deny').click();await reopened.locator('#native-signin').waitFor({state:'hidden'});
      check(await reopened.locator('#login').isVisible(),`${locale}: cancelling browser approval leaves the report usable`);
      await app.close();await system.close();
    }
    check(!requests.some(v=>v.startsWith('/api/reports')),'authorization never submits reports or logs');
    assert.deepEqual(errors,[]);checks.push('no page or fixture errors');
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,checks,realDiscordPosts:0},null,2));
    console.log(JSON.stringify({passed:true,checks}));
  }catch(error){fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:false,checks,error:String(error),errors},null,2));throw error;}
  finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
