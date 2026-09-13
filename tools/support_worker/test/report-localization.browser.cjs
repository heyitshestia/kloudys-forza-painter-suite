const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url'),{gzipSync}=require('node:zlib'),{chromium}=require('playwright');

(async()=>{
  const output=path.resolve(process.argv[2]);fs.mkdirSync(output,{recursive:true});
  const load=name=>import(pathToFileURL(path.join(__dirname,name)));
  const {logBlob,logMetadata}=await load('log-fixture.mjs');
  const {readSubmission}=await load('../src/submission.mjs');
  const {korean}=await load('../public/report-ko.mjs');
  const root=path.join(__dirname,'../public'),allowed=new Set(fs.readdirSync(root));
  const server=http.createServer((req,res)=>{
    const name=new URL(req.url,'http://localhost').pathname.slice(1)||'index.html';
    if(!allowed.has(name)){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'Content-Type':name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':name.endsWith('.png')?'image/png':'text/javascript'});
    res.end(fs.readFileSync(path.join(root,name)));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`,checks=[],errors=[],posts=[];
  const check=(ok,name)=>{assert.ok(ok,name);checks.push(name);};
  const report={schema:'kfps-support-report/1',id:crypto.randomUUID(),feature:'Editor',source:'kfps',title:'Send report',description:'English and 한국어 user text stays unchanged.',technical:{app:{version:'test'}},private_logs:logMetadata};
  const prepared=gzipSync(JSON.stringify({schema:'kfps-support-package/1',report,logs_base64:Buffer.from(await logBlob.arrayBuffer()).toString('base64')}));
  let browser,page;
  try{
    browser=await chromium.launch({channel:'chrome',headless:true});
    const context=await browser.newContext({locale:'en-US',viewport:{width:1080,height:900}});
    await context.addInitScript(()=>{Object.defineProperty(window,'KFPSNativeReport',{value:true});Object.defineProperty(window,'KFPSReportSystemLanguage',{value:'ko'});});
    page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
    const png=await page.screenshot({clip:{x:0,y:0,width:32,height:32}});
    let delivered=false;
    await page.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url());if(url.origin!==origin)return route.abort();
      if(url.pathname==='/api/config')return route.fulfill({json:{enabled:true,join_url:'https://discord.gg/XT8dG8bDKy'}});
      if(url.pathname==='/api/session')return route.fulfill({json:{authenticated:true,name:'Synthetic User',csrf:'test'}});
      if(url.pathname.startsWith('/api/reports')){
        if(req.method()==='POST'){
          posts.push(await readSubmission(new Request(req.url(),{method:'POST',headers:req.headers(),body:req.postDataBuffer()})));
          if(posts.length===1)return route.fulfill({status:503,json:{error:'The reporting service could not complete this request. Your local report is safe.'}});
          delivered=true;
        }
        return route.fulfill({json:{status:delivered?'delivered':'retryable',message:delivered?'Report sent to the KFPS Support server. Open your public post below. Any included technical details remain private to staff.':'Delivery is incomplete. Retry this same report after the wait shown; already delivered parts will not be posted again.',retry_after:0}});
      }
      return route.continue();
    });
    await page.goto(origin+'/#bundle='+prepared.toString('base64url'));
    await page.waitForFunction(()=>!document.getElementById('send').disabled);
    check(await page.locator('html').getAttribute('lang')==='ko','Windows Korean display overrides English browser region');
    check(await page.locator('h1').innerText()==='어떤 문제가 있었나요?','Korean first screen is natural and complete');
    check(await page.locator('#saved-report-recovery').isHidden(),'native window has no manual log picker');
    await page.screenshot({path:path.join(output,'korean-startup-preview.png')});
    for(const value of ['Generator','Editor','Import and export','Liveries','Community','Updater','Other']){
      await page.locator('#feature').selectOption(value);
      check(await page.locator('#feature').inputValue()===value&&await page.locator('#feature option:checked').innerText()===korean[value],`localized feature ${value} keeps its protocol value`);
    }
    await page.locator('#feature').selectOption('Editor');
    await page.locator('#description').fill('');await page.locator('#send').click();
    check((await page.locator('#notice').innerText()).includes('5자 이상'),'required description error is Korean even with English browser region');
    check(posts.length===0&&await page.locator('#receipt').isHidden(),'validation failure neither submits nor freezes the draft');
    await page.locator('#description').fill(report.description);
    await page.evaluate(()=>{const create=window.createImageBitmap;window.createImageBitmap=async(...args)=>{await new Promise(r=>setTimeout(r,250));return create(...args);};});
    await page.locator('#screenshots').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:png});
    await page.locator('#report-language').selectOption('en');
    await page.waitForFunction(()=>document.querySelectorAll('#screenshot-previews figure').length===1&&!document.getElementById('send').disabled);
    await page.locator('#screenshots-public').check();
    const beforeUrl=page.url();
    await page.locator('#report-language').selectOption('ko');
    check(page.url()===beforeUrl&&await page.locator('#screenshot-previews figure').count()===1,'in-place switch during screenshot preparation preserves the image');
    check(await page.locator('#screenshots-public').isChecked(),'switch preserves public screenshot consent');
    check(await page.locator('#description').inputValue()===report.description&&await page.locator('#title').inputValue()==='Send report','authored bilingual text and title are never translated');
    check(await page.locator('#screenshot-previews button').innerText()==='제거','screenshot commands are Korean');
    await page.locator('#screenshots').setInputFiles(Array.from({length:4},(_,i)=>({name:`test-${i}.png`,mimeType:'image/png',buffer:png})));
    await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('최대 3장'));
    check(await page.locator('#screenshot-previews figure').count()===1,'Korean image-limit error preserves previously accepted image');
    for(const locale of ['ko','en']){
      await page.locator('#report-language').selectOption(locale);
      for(const width of [1080,520,390]){
        await page.setViewportSize({width,height:900});
        check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${locale} has no overflow at ${width}px`);
        await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(output,`form-${locale}-${width}.png`)});
        await page.locator('#private-logs-section').evaluate(e=>e.scrollIntoView({block:'start'}));await page.screenshot({path:path.join(output,`logs-${locale}-${width}.png`)});
        await page.locator('#report-privacy').evaluate(e=>e.scrollIntoView({block:'start'}));await page.screenshot({path:path.join(output,`privacy-${locale}-${width}.png`)});
      }
    }
    await page.locator('#report-language').selectOption('ko');
    await page.locator('#send').click();await page.locator('#receipt[data-status="unknown"]').waitFor();
    check((await page.locator('#result-text').innerText()).includes('전송 결과'),'delivery failure has a Korean recovery message');
    await page.locator('#check').click();await page.locator('#retry').waitFor({state:'visible'});
    check((await page.locator('#result-text').innerText()).includes('아직 전송이 완료되지'),'partial delivery state is Korean');
    await page.locator('#report-language').selectOption('en');
    check(await page.locator('#result-title').innerText()==='Report delivery','language switch redraws a receipt without another network submission');
    check(posts.length===1,'switching receipt language never submits');
    await page.locator('#report-language').selectOption('ko');await page.locator('#retry').click();
    await page.locator('#receipt[data-status="delivered"]').waitFor();
    check(await page.locator('#result-title').innerText()==='보고서가 전송되었습니다','successful delivery is Korean');
    assert.deepEqual(posts[0].report,posts[1].report);
    for(const post of posts){assert.deepEqual(Buffer.from(await post.privateLogs.arrayBuffer()),Buffer.from(await logBlob.arrayBuffer()));assert.equal(post.files.length,1);}
    checks.push('retry keeps exact frozen report, compressed logs and public screenshot despite language switches');
    await page.locator('#report-language').selectOption('en');await page.reload();
    await page.locator('#receipt[data-status="delivered"]').waitFor();
    check(await page.locator('html').getAttribute('lang')==='en','manual language survives reload with Korean system setting');
    await page.close();const reopened=await context.newPage();
    await reopened.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    await reopened.goto(origin);await reopened.locator('#report-language').waitFor();
    check(await reopened.locator('html').getAttribute('lang')==='en','manual language survives closing and reopening');
    await reopened.locator('#report-language').selectOption('auto');
    check(await reopened.locator('html').getAttribute('lang')==='ko','System language restores automatic detection');
    await context.close();
    const blocked=await browser.newContext({locale:'en-US'});
    await blocked.addInitScript(()=>{Object.defineProperty(window,'KFPSReportSystemLanguage',{value:'ko'});Storage.prototype.getItem=()=>{throw Error('disabled storage');};Storage.prototype.setItem=()=>{throw Error('disabled storage');};});
    const offline=await blocked.newPage();offline.on('pageerror',e=>errors.push(String(e)));
    await offline.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    await offline.goto(origin);await offline.locator('#report-language').selectOption('en');
    check(await offline.locator('html').getAttribute('lang')==='en','manual switch works for the session even when storage is blocked');
    await blocked.close();check(!errors.length,'no JavaScript errors');
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:true,checks,realDiscordPosts:0},null,2));console.log(JSON.stringify({passed:true,checks}));
  }catch(error){
    const state=await page?.evaluate(()=>({notice:document.getElementById('notice')?.textContent,language:document.documentElement.lang,images:document.querySelectorAll('#screenshot-previews figure').length,sendDisabled:document.getElementById('send')?.disabled})).catch(()=>null);
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({passed:false,checks,error:String(error),errors,state},null,2));throw error;
  }
  finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
