const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict'),zlib=require('node:zlib');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

(async()=>{
  const output=path.resolve(process.argv[2]);fs.mkdirSync(output,{recursive:true});
  const {readSubmission}=await import(pathToFileURL(path.join(__dirname,'../src/submission.mjs')));
  const {describePrivateLogs,LOG_SCHEMA,APP_LOG_SCHEMA,PACKAGE_SCHEMA}=await import(pathToFileURL(path.join(__dirname,'../public/private-logs.mjs')));
  const {redact,normalizeReport}=await import(pathToFileURL(path.join(__dirname,'../public/protocol.mjs')));
  const root=path.join(__dirname,'../public'),allowed=new Set(fs.readdirSync(root));
  const server=http.createServer((req,res)=>{
    const name=new URL(req.url,'http://localhost').pathname.slice(1)||'index.html';
    if(!allowed.has(name)){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'Content-Type':name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':name.endsWith('.png')?'image/png':'text/javascript'});
    res.end(fs.readFileSync(path.join(root,name)));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  const appLogs=process.argv[3]==='app';
  const bundle={schema:appLogs?APP_LOG_SCHEMA:LOG_SCHEMA,created_at:new Date().toISOString(),files:[{name:appLogs?'transfer-worker-0001.log':'desktop.log',modified_utc:new Date().toISOString(),source_bytes:10000,omitted_lines:0,text:'Actual log fixture line\n'.repeat(1000)}],warnings:[]};
  const logs=new Blob([zlib.gzipSync(JSON.stringify(bundle))],{type:'application/gzip'});
  const metadata=(await describePrivateLogs(logs,{redact})).metadata;
  const makeReport=()=>normalizeReport({schema:'kfps-support-report/1',id:crypto.randomUUID(),feature:'Editor',description:'Private full log browser test',private_logs:metadata});
  const packageFor=report=>zlib.gzipSync(JSON.stringify({schema:PACKAGE_SCHEMA,report,logs_base64:Buffer.from(zlib.gzipSync(JSON.stringify(bundle))).toString('base64')}));
  const checks=[],posts=[],errors=[];let browser,authenticated=false,status='retryable';
  const check=(ok,name)=>{assert.ok(ok,name);checks.push(name);};
  try {
    browser=await chromium.launch({channel:'chrome',headless:true});
    const page=await browser.newPage({viewport:{width:1280,height:960}});
    page.on('pageerror',error=>errors.push(String(error)));
    await page.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url());if(url.origin!==origin)return route.abort();
      if(url.pathname==='/api/config')return route.fulfill({json:{enabled:true,join_url:'https://discord.gg/XT8dG8bDKy'}});
      if(url.pathname==='/api/session')return route.fulfill({json:{authenticated,name:'Test Owner',csrf:'test'}});
      if(url.pathname==='/auth/start'){authenticated=true;return route.fulfill({status:303,headers:{Location:origin}});}
      if(url.pathname.startsWith('/api/reports')) {
        if(req.method()==='POST')posts.push(await readSubmission(new Request(req.url(),{method:'POST',headers:req.headers(),body:req.postDataBuffer()})));
        return route.fulfill({json:{status,message:'Local verification; no Discord post.',retry_after:0}});
      }
      return route.continue();
    });
    const initial=makeReport(),packageBytes=packageFor(initial);
    await page.goto(origin+'/#bundle='+packageBytes.toString('base64url'));
    await page.waitForFunction(()=>!document.getElementById('download-private-logs').hidden);
    check(!page.url().includes('#'),'private handoff fragment cleared');
    check(posts.length===0,'preparing full logs does not upload them');
    check(await page.locator('#private-logs-section').isVisible(),'private destination explained separately');
    await page.locator('#login').click();await page.getByText('Signed in as Test Owner',{exact:true}).waitFor();
    check(await page.locator('#download-private-logs').isVisible(),'full logs survive sign-in redirect');
    check(!(await page.evaluate(()=>sessionStorage.getItem('kfps-support-draft-v1'))).includes('Actual log fixture'),'full text is not placed in sessionStorage');
    await page.reload();await page.waitForFunction(()=>!document.getElementById('download-private-logs').hidden);
    check(true,'full logs survive refresh from bounded local storage');
    await page.locator('#description').fill('Edited description that must survive retries.');
    for(const width of [1280,390]) {
      await page.setViewportSize({width,height:960});check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`no overflow at ${width}`);
      await page.screenshot({path:path.join(output,`private-logs-${width}.png`),fullPage:true});
    }
    await page.locator('#send').click();await page.locator('#retry').waitFor({state:'visible'});
    check(posts.length===1&&posts[0].privateLogs,'actual multipart parser received full private logs');
    assert.deepEqual(Buffer.from(await posts[0].privateLogs.arrayBuffer()),Buffer.from(await logs.arrayBuffer()));
    const frozen=JSON.stringify(posts[0].report);
    await page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('kfps-private-report-logs-v1');r.onsuccess=()=>{const db=r.result,t=db.transaction('bundle','readwrite');t.objectStore('bundle').clear();t.oncomplete=()=>{db.close();resolve();};t.onerror=()=>reject(t.error);};}));
    await page.reload();await page.locator('#retry').waitFor({state:'visible'});
    await page.locator('#retry').click();check(posts.length===1,'missing archive never silently omitted on retry');
    await page.locator('#check').click();await page.locator('#retry').waitFor({state:'visible'});
    const upload={name:'report.kfps-report.json.gz',mimeType:'application/gzip',buffer:packageBytes};
    await page.locator('#report-file').setInputFiles(upload);
    await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('Original private logs restored'));
    status='delivered';await page.locator('#retry').click();await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    check(posts.length===2&&JSON.stringify(posts[1].report)===frozen,'retry reattachment preserves edited report and receipt hash');
    await page.waitForTimeout(250);
    const stored=await page.evaluate(()=>new Promise(resolve=>{const r=indexedDB.open('kfps-private-report-logs-v1');r.onsuccess=()=>{const db=r.result,t=db.transaction('bundle'),q=t.objectStore('bundle').get('current');q.onsuccess=()=>resolve(q.result||null);t.oncomplete=()=>db.close();};}));
    check(!stored,'successful delivery removes temporary browser log copy');
    await page.reload();await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();check(posts.length===2,'receipt reload does not resend logs');
    const excluded=makeReport();await page.goto('about:blank');await page.goto(origin+'/#bundle='+packageFor(excluded).toString('base64url'));
    await page.waitForFunction(()=>!document.getElementById('download-private-logs').hidden);
    await page.locator('#include').uncheck();await page.locator('#send').click();await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    check(!posts[2].privateLogs&&!posts[2].report.private_logs,'technical-details opt-out sends no log archive');
    await page.goto('about:blank');await page.goto(origin+'/#bundle='+packageFor(makeReport()).toString('base64url'));
    await page.waitForFunction(()=>!document.getElementById('download-private-logs').hidden);
    await page.evaluate(()=>new Promise(resolve=>{
      const r=indexedDB.open('kfps-private-report-logs-v1');r.onsuccess=()=>{const db=r.result,t=db.transaction('bundle','readwrite'),s=t.objectStore('bundle'),q=s.get('current');
        q.onsuccess=()=>s.put({...q.result,at:Date.now()-25*60*60*1000},'current');t.oncomplete=()=>{db.close();
          const value=JSON.parse(sessionStorage.getItem('kfps-support-draft-v1'));delete value.draft.private_logs;sessionStorage.setItem('kfps-support-draft-v1',JSON.stringify(value));resolve();};};
    }));
    await page.reload();await page.getByText('Signed in as Test Owner',{exact:true}).waitFor();
    const expired=await page.evaluate(()=>new Promise(resolve=>{const r=indexedDB.open('kfps-private-report-logs-v1');r.onsuccess=()=>{const db=r.result,t=db.transaction('bundle'),q=t.objectStore('bundle').get('current');q.onsuccess=()=>resolve(q.result||null);t.oncomplete=()=>db.close();};}));
    check(!expired,'expired archive is purged even when opening a report without private logs');
    check(await page.locator('#send').isDisabled(),'checked summary-only draft blocks Send');
    const attempts=posts.length;
    await page.locator('#report-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
    await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('Sending is blocked'));
    check(posts.length===attempts,'programmatic or Enter submission cannot bypass required logs');
    check(await page.locator('#receipt').isHidden(),'missing local attachment leaves an editable draft, not a phantom receipt');
    await page.locator('#include').uncheck();check(await page.locator('#send').isEnabled(),'explicit opt-out enables a summary-only draft');
    await page.locator('#include').check();check(await page.locator('#send').isDisabled(),'checking the box again reinstates the log requirement');
    await page.locator('#include').uncheck();await page.locator('#send').click();await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    check(posts.length===attempts+1&&!posts.at(-1).privateLogs&&posts.at(-1).report.include_technical===false,'missing-log report can send only after explicit opt-out');
    check(errors.length===0,'no JavaScript errors');
    const result={passed:true,checks,realDiscordPosts:0,errors};fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  } finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
