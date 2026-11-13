const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {test,before,after}=require('node:test');
const {gzipSync}=require('node:zlib');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
const {PNG}=require('pngjs');
const KEY='kfps-support-draft-v1';
const output=process.env.KFPS_FRONTEND_OUTPUT&&path.resolve(process.env.KFPS_FRONTEND_OUTPUT);
let browser,server,origin,fixture,readSubmission;
const results=[];
before(async()=>{
  fixture=await import(pathToFileURL(path.join(__dirname,'log-fixture.mjs')));
  ({readSubmission}=await import(pathToFileURL(path.join(__dirname,'../src/submission.mjs'))));
  const root=path.join(__dirname,'../public'),allowed=new Set(fs.readdirSync(root));
  server=http.createServer((req,res)=>{
    const name=new URL(req.url,'http://localhost').pathname.slice(1)||'index.html';
    if(!allowed.has(name)){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'Content-Type':name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':name.endsWith('.png')?'image/png':'text/javascript'});
    res.end(fs.readFileSync(path.join(root,name)));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  origin=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch({channel:'chrome',headless:true});
  if(output)fs.mkdirSync(output,{recursive:true});
});
after(async()=>{
  await browser?.close();if(server)await new Promise(resolve=>server.close(resolve));
  if(output)fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({results,realDiscordPosts:0},null,2));
});
function report(extra={}) {return {schema:'kfps-support-report/1',id:crypto.randomUUID(),created_at:'2026-11-13T12:00:00Z',source:'kfps',feature:'Editor',description:'Original fixture problem',title:'Fixture title',expected:'',include_technical:true,technical:{app:{version:'3.2.3'},hardware:{platform:'Windows fixture'}},private_logs:fixture.logMetadata,...extra};}
async function pack(value){return gzipSync(JSON.stringify({schema:'kfps-support-package/1',report:value,logs_base64:Buffer.from(await fixture.logBlob.arrayBuffer()).toString('base64')}));}
async function harness(t,{native=true,authenticated=true}={}) {
  const context=await browser.newContext({viewport:{width:1280,height:960},serviceWorkers:'block'}),posts=[],errors=[],external=[];
  if(native)await context.addInitScript(()=>{window.KFPSNativeReport=true;});
  const state={authenticated,status:'retryable',authFailure:false,postDelay:0,postFailure:false,statusFailure:false};
  await context.route('**/*',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(url.origin!==origin){external.push(req.url());return route.abort();}
    if(url.pathname==='/api/config')return route.fulfill({json:{enabled:true,join_url:origin+'/invite'}});
    if(url.pathname==='/api/session')return route.fulfill({json:{authenticated:state.authenticated,name:'Fixture User',csrf:'fixture'}});
    if(url.pathname==='/auth/logout'){state.authenticated=false;return route.fulfill({json:{ok:true}});}
    if(url.pathname==='/api/native-auth/start')return state.authFailure?route.fulfill({status:503,json:{error:'Unavailable'}}):route.fulfill({json:{id:'11111111-1111-4111-8111-111111111111',url:origin+'/auth/native?ticket=11111111-1111-4111-8111-111111111111',code:'ABCD-1234',expires_at:Date.now()+300000,expires_in_ms:300000}});
    if(url.pathname==='/api/native-auth/poll'){state.authenticated=true;return route.fulfill({json:{status:'ready'}});}
    if(url.pathname==='/auth/start')return route.fulfill({status:303,headers:{Location:origin+'/?auth=cancelled'}});
    if(url.pathname.startsWith('/api/reports')){
      if(req.method()==='POST'){
        posts.push(await readSubmission(new Request(req.url(),{method:'POST',headers:req.headers(),body:req.postDataBuffer()})));
        if(state.postDelay)await new Promise(resolve=>setTimeout(resolve,state.postDelay));
        if(state.postFailure)return route.abort();
      }else if(state.statusFailure)return route.fulfill({status:503,json:{error:'Unavailable'}});
      return route.fulfill({json:{status:state.status,message:'Local fixture status',retry_after:0,public_url:state.publicUrl||null}});
    }
    return route.continue();
  });
  const page=await context.newPage();page.setDefaultTimeout(5000);
  context.on('page',p=>p.on('pageerror',e=>errors.push(String(e))));page.on('pageerror',e=>errors.push(String(e)));
  t.after(async()=>{results.push({name:t.name,status:t.passed?'passed':t.error?'failed':'completed',submissions:posts.length,errors,external});await context.close();assert.deepEqual(errors,[]);assert.deepEqual(external,[]);});
  async function ready(p=page){await p.waitForFunction(()=>!!window.KFPSReportTransfer);}
  async function open(value=report()){await page.goto(origin+'/#bundle='+(await pack(value)).toString('base64url'));await ready();return value;}
  async function transfer(value){const bytes=await pack(value);await page.evaluate(async({id,encoded})=>{
    const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
    const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
    KFPSReportTransfer.begin({id,mode:'package',size:bytes.length,sha256});KFPSReportTransfer.chunk(0,encoded);KFPSReportTransfer.finish();
  },{id:value.id,encoded:bytes.toString('base64')});await page.waitForFunction(id=>['ready','error'].includes(KFPSReportTransfer.status(id).state),value.id);}
  const saved=()=>page.evaluate(key=>JSON.parse(localStorage.getItem(key)||sessionStorage.getItem(key)),KEY);
  const cached=()=>page.evaluate(()=>new Promise((resolve,reject)=>{const r=indexedDB.open('kfps-private-report-logs-v1');r.onerror=()=>reject(r.error);r.onsuccess=()=>{const db=r.result,tx=db.transaction('bundle'),q=tx.objectStore('bundle').get('current');q.onsuccess=()=>resolve(q.result?.id||null);tx.oncomplete=()=>db.close();};}));
  return {context,page,posts,state,errors,external,open,ready,transfer,saved,cached};
}
test('short and unfinished draft fields survive reload without relaxing submission validation',async t=>{
  const h=await harness(t);await h.open();
  for(const text of ['lag','  ','','a']){
    await h.page.locator('#description').fill(text);await h.page.locator('#title').fill('');
    await h.page.reload();await h.ready();
    assert.equal(await h.page.locator('#description').inputValue(),text);
    assert.equal(await h.page.locator('#title').inputValue(),'');
    await h.page.locator('#send').click();assert.equal(h.posts.length,0);assert(await h.page.locator('#receipt').isHidden());
  }
});
test('consent-off reload retains local metadata and exact log pairing, but excludes them from sends',async t=>{
  const h=await harness(t),initial=await h.open();
  await h.page.locator('#include').uncheck();await h.page.reload();await h.ready();
  assert.equal(await h.page.locator('#version').inputValue(),'3.2.3');
  assert.equal((await h.saved()).draft.private_logs.sha256,initial.private_logs.sha256);
  assert.equal(await h.cached(),initial.id);
  await h.page.locator('#include').check();assert(await h.page.locator('#send').isEnabled());
  await h.page.locator('#include').uncheck();await h.page.locator('#send').click();await h.page.locator('#receipt').waitFor({state:'visible'});
  assert.equal(h.posts.length,1);assert.deepEqual(h.posts[0].report.technical,{});assert(!h.posts[0].privateLogs);
});
test('fresh-ID native reopen stages a choice without overwriting saved draft or private archive',async t=>{
  const h=await harness(t),initial=await h.open();await h.page.locator('#description').fill('My unfinished old report');
  await h.page.evaluate(()=>sessionStorage.clear());await h.page.reload();await h.ready();
  const incoming=report({description:'New report snapshot'});await h.transfer(incoming);
  assert.equal(await h.page.evaluate(id=>KFPSReportTransfer.status(id).waiting_user,incoming.id),true);
  assert.equal((await h.saved()).draft.id,initial.id);assert.equal(await h.cached(),initial.id);
  assert.equal(await h.page.locator('#description').inputValue(),'My unfinished old report');
  assert(await h.page.locator('#incoming-report').isVisible());
  await h.page.locator('#resume-report').click();assert.equal((await h.saved()).draft.id,initial.id);
  assert.equal(await h.page.evaluate(id=>!!KFPSReportTransfer.status(id).waiting_user,incoming.id),false);
  await h.transfer(incoming);await h.page.locator('#replace-report').click();
  await h.page.waitForFunction(id=>document.querySelector('#report-id').textContent.includes(id),incoming.id);
  assert.equal((await h.saved()).draft.id,incoming.id);assert.equal(await h.cached(),incoming.id);assert.equal(h.posts.length,0);
});
test('saved package import preserves same-ID edits and asks before replacing another report',async t=>{
  const h=await harness(t,{native:false}),initial=await h.open();await h.page.locator('#description').fill('Edited current report');
  const upload=async value=>h.page.locator('#report-file').setInputFiles({name:'saved.json.gz',mimeType:'application/gzip',buffer:await pack(value)});
  await upload(initial);await h.page.waitForFunction(()=>document.querySelector('#report-file').value==='');
  assert.equal(await h.page.locator('#description').inputValue(),'Edited current report');
  const other=report();await upload(other);await h.page.locator('#incoming-report').waitFor({state:'visible'});
  assert.equal(await h.cached(),initial.id);await h.page.locator('#resume-report').click();assert.equal(h.posts.length,0);
});
test('unconfirmed receipts cannot be replaced; retry preserves identity and duplicate sends stay blocked',async t=>{
  const h=await harness(t),initial=await h.open();await h.page.locator('#description').fill('Edited submitted description');
  h.state.postDelay=300;await h.page.locator('#send').dblclick();await h.page.locator('#retry').waitFor({state:'visible'});
  assert.equal(h.posts.length,1);const frozen=JSON.stringify(h.posts[0].report);
  const other=report();await h.transfer(other);
  assert.equal((await h.saved()).submitted.id,initial.id);assert.equal(await h.cached(),initial.id);
  assert(await h.page.locator('#replace-report').isDisabled());await h.page.locator('#resume-report').click();
  h.state.status='delivered';await h.page.locator('#retry').dblclick();await h.page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
  assert.equal(h.posts.length,2);assert.equal(JSON.stringify(h.posts[1].report),frozen);
  await h.page.locator('#report-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  assert.equal(h.posts.length,2);
  await h.transfer(other);assert(await h.page.locator('#replace-report').isEnabled());await h.page.locator('#replace-report').click();
  await h.page.waitForFunction(id=>document.querySelector('#report-id').textContent.includes(id),other.id);
  assert.equal((await h.saved()).submitted,null);assert.equal(await h.cached(),other.id);
});
test('known delivered receipt survives failed status checks after reload and cannot be retried',async t=>{
  const h=await harness(t),initial=await h.open();h.state.status='delivered';
  await h.page.locator('#include').uncheck();await h.page.locator('#send').click();await h.page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
  h.state.statusFailure=true;await h.page.reload();await h.ready();
  assert.equal(await h.page.locator('#result-title').textContent(),'Report sent');
  assert(await h.page.locator('#retry').isHidden());assert((await h.page.locator('#receipt-id').textContent()).includes(initial.id));
  await h.page.locator('#retry').evaluate(button=>button.click());assert.equal(h.posts.length,1);
});
test('lost send response and restart preserve frozen receipt; missing logs cannot silently resend',async t=>{
  const h=await harness(t),initial=await h.open();h.state.postFailure=true;
  await h.page.locator('#send').click();await h.page.locator('#receipt').waitFor({state:'visible'});
  assert.equal(h.posts.length,1);const frozen=JSON.stringify((await h.saved()).submitted);
  await h.page.reload();await h.ready();assert.equal(h.posts.length,1);assert.equal(JSON.stringify((await h.saved()).submitted),frozen);
  await h.page.evaluate(()=>new Promise(resolve=>{const r=indexedDB.deleteDatabase('kfps-private-report-logs-v1');r.onsuccess=resolve;}));
  await h.page.reload();await h.ready();await h.page.locator('#retry').click();assert.equal(h.posts.length,1);
  await h.transfer(initial);h.state.postFailure=false;h.state.status='delivered';await h.page.locator('#retry').click();
  await h.page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();assert.equal(JSON.stringify(h.posts[1].report),frozen);
});
test('native sign-in failure and retry retain draft, attachments and never submit automatically',async t=>{
  const h=await harness(t,{authenticated:false}),initial=await h.open();await h.page.locator('#description').fill('lag');
  h.state.authFailure=true;await h.page.locator('#login').click();await h.page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('temporarily unavailable'));
  assert(await h.page.locator('#login').isEnabled());h.state.authFailure=false;await h.page.locator('#login').click();
  await h.page.getByText('Signed in as Fixture User',{exact:true}).waitFor();
  assert.equal(await h.page.locator('#description').inputValue(),'lag');assert.equal(await h.cached(),initial.id);assert.equal(h.posts.length,0);
});
for(const phase of ['module','config'])test(`logout reload keeps sign-in disabled while ${phase} initialization is explicitly held`,async t=>{
  const h=await harness(t);await h.open();let release,entered;
  const gate=new Promise(resolve=>{release=resolve;}),blocked=new Promise(resolve=>{entered=resolve;});
  const target=phase==='module'?'**/form.js':'**/api/config';
  await h.page.route(target,async route=>{entered();await gate;
    if(phase==='module')return route.continue();
    return route.fulfill({json:{enabled:true,join_url:origin+'/invite'}});
  });
  try {
    const navigated=h.page.waitForEvent('framenavigated',frame=>frame===h.page.mainFrame());
    await h.page.locator('#logout').click();await navigated;await blocked;
    await h.page.locator('#login').waitFor({state:'visible'});
    const snapshot=await h.page.evaluate(()=>({readyState:document.readyState,loginDisabled:document.querySelector('#login').disabled,
      handlerInstalled:typeof document.querySelector('#login').onclick==='function',signInBridge:!!window.KFPSReportSignIn,transferBridge:!!window.KFPSReportTransfer}));
    results.push({name:t.name,heldInitialization:snapshot});
    assert.equal(snapshot.transferBridge,false);assert.equal(snapshot.handlerInstalled,phase==='config');
    assert.equal(snapshot.loginDisabled,true,JSON.stringify(snapshot));
    release();await h.ready();assert(await h.page.locator('#login').isEnabled());
    await h.page.locator('#login').click();await h.page.waitForFunction(()=>!!window.KFPSReportSignIn.request());
    assert.equal(h.posts.length,0);
  }finally{release();}
});
test('cancelled browser sign-in retains short draft and logs through navigation',async t=>{
  const h=await harness(t,{native:false,authenticated:false}),initial=await h.open();await h.page.locator('#description').fill('lag');
  await h.page.locator('#login').click();await h.ready();
  assert.equal(await h.page.locator('#description').inputValue(),'lag');assert.equal(await h.cached(),initial.id);assert.equal(h.posts.length,0);
  assert((await h.page.locator('#notice').textContent()).includes('cancelled'));
});
function screenshot(color=120){const png=new PNG({width:8,height:8});for(let i=0;i<png.data.length;i+=4){png.data[i]=color;png.data[i+1]=90;png.data[i+2]=30;png.data[i+3]=255;}return {name:'private-original-name.png',mimeType:'image/png',buffer:PNG.sync.write(png)};}
test('screenshots require public consent and exact reattachment after reload before retry',async t=>{
  const h=await harness(t);await h.open();
  await h.page.locator('#screenshots').setInputFiles(screenshot());await h.page.locator('#screenshot-previews img').waitFor();
  await h.page.locator('#send').click();assert.equal(h.posts.length,0);assert(await h.page.locator('#receipt').isHidden());
  await h.page.locator('#screenshots-public').check();await h.page.locator('#send').click();await h.page.locator('#receipt').waitFor({state:'visible'});
  const frozen=JSON.stringify(h.posts[0].report);assert.equal(h.posts.length,1);
  await h.page.reload();await h.ready();await h.page.locator('#retry').click();assert.equal(h.posts.length,1);
  await h.page.locator('#screenshots').setInputFiles(screenshot(220));await h.page.locator('#screenshot-previews img').waitFor();
  await h.page.locator('#retry').click();assert.equal(h.posts.length,1);await h.page.getByRole('button',{name:'Remove screenshot 1',exact:true}).click();
  await h.page.locator('#screenshots').setInputFiles(screenshot());await h.page.locator('#screenshot-previews img').waitFor();
  h.state.status='delivered';await h.page.locator('#retry').click();await h.page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
  assert.equal(h.posts.length,2);assert.equal(JSON.stringify(h.posts[1].report),frozen);
});
test('import during an active send cannot replace its report or archive',async t=>{
  const h=await harness(t),initial=await h.open();h.state.postDelay=1000;
  await h.page.locator('#send').click();await h.transfer(report());
  assert.equal((await h.saved()).submitted.id,initial.id);assert.equal(await h.cached(),initial.id);
  await h.page.locator('#receipt').waitFor({state:'visible'});assert.equal(h.posts.length,1);
});
test('clearing an imported game choice removes stale game context from the saved draft',async t=>{
  const h=await harness(t);await h.open(report({technical:{app:{version:'3.2.3'},running_games:[{game:'FH5',store:'steam'}]}}));
  await h.page.getByText('Missing context',{exact:true}).click();
  await h.page.locator('#game').selectOption('');await h.page.locator('#version').fill('');await h.page.locator('#description').fill('Game selection is now unknown');await h.page.reload();await h.ready();
  assert.equal(await h.page.locator('#game').inputValue(),'');assert.deepEqual((await h.saved()).draft.technical.running_games,[]);
  assert.equal(await h.page.locator('#version').inputValue(),'');
});
test('invalid imports preserve the current draft and archive, including same-ID log mismatches',async t=>{
  const h=await harness(t,{native:false}),initial=await h.open();await h.page.locator('#description').fill('Current edited text');
  for(const buffer of [Buffer.from('{broken'),Buffer.from(JSON.stringify({...initial,private_logs:{...initial.private_logs,sha256:'0'.repeat(64)}}))]){
    await h.page.locator('#report-file').setInputFiles({name:'bad.json',mimeType:'application/json',buffer});
    await h.page.waitForFunction(()=>document.querySelector('#report-file').value==='');
    assert.equal((await h.saved()).draft.id,initial.id);assert.equal(await h.cached(),initial.id);
    assert.equal(await h.page.locator('#description').inputValue(),'Current edited text');assert(await h.page.locator('#incoming-report').isHidden());
  }
});
test('unavailable local log storage keeps the warning visible while preserving the live attachment',async t=>{
  const h=await harness(t);await h.context.addInitScript(()=>{IDBFactory.prototype.open=function(){throw Error('Fixture storage denied');};});
  await h.open();assert.match(await h.page.locator('#notice').textContent(),/could not be cached/i);
  assert(await h.page.locator('#notice').evaluate(el=>el.classList.contains('error')));
  assert(await h.page.locator('#send').isEnabled());await h.page.locator('#send').click();await h.page.locator('#receipt').waitFor({state:'visible'});assert.equal(h.posts.length,1);
});
test('failed replacement draft save cannot overwrite the old draft or private archive',async t=>{
  const h=await harness(t),initial=await h.open();await h.page.locator('#description').fill('Keep this old edited draft');
  const next=report();await h.transfer(next);
  await h.page.evaluate(({key,id})=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage&&k===key&&JSON.parse(v).draft.id===id)throw Error('Fixture quota exceeded');return original.call(this,k,v);};},{key:KEY,id:next.id});
  await h.page.locator('#replace-report').click();
  await h.page.waitForFunction(()=>document.querySelector('#notice').classList.contains('error'));
  assert.equal((await h.saved()).draft.id,initial.id);assert.equal(await h.cached(),initial.id);
  assert.equal(await h.page.locator('#description').inputValue(),'Keep this old edited draft');
  assert(await h.page.locator('#incoming-report').isVisible());
  await h.page.reload();await h.ready();assert.equal((await h.saved()).draft.id,initial.id);assert.equal(await h.cached(),initial.id);
});
test('interrupted log promotion recovers the exact staged archive after reload',async t=>{
  const h=await harness(t),initial=await h.open(),next=report();await h.transfer(next);
  await h.page.evaluate(()=>{const original=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(value,key){if(key==='current')throw Error('Fixture interrupted promotion');return original.call(this,value,key);};});
  await h.page.locator('#replace-report').click();
  await h.page.waitForFunction(id=>document.querySelector('#report-id').textContent.includes(id),next.id);
  assert.equal((await h.saved()).draft.id,next.id);assert.equal(await h.cached(),initial.id);
  await h.page.reload();await h.ready();assert.equal(await h.cached(),next.id);
  assert(await h.page.locator('#send').isEnabled());assert.equal(await h.page.locator('#description').inputValue(),next.description);
});
test('a second replacement cannot erase an unpromoted archive needed by the saved draft',async t=>{
  const h=await harness(t);await h.open();const next=report();await h.transfer(next);
  await h.page.evaluate(()=>{const original=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(value,key){if(key==='current')throw Error('Fixture interrupted promotion');return original.call(this,value,key);};});
  await h.page.locator('#replace-report').click();await h.page.waitForFunction(id=>document.querySelector('#report-id').textContent.includes(id),next.id);
  const later=report();await h.transfer(later);
  await h.page.evaluate(({key,id})=>{const now=Date.now;Date.now=()=>now()+61000;const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage&&k===key&&JSON.parse(v).draft.id===id)throw Error('Fixture quota exceeded');return original.call(this,k,v);};},{key:KEY,id:later.id});
  await h.page.locator('#replace-report').click();await h.page.reload();await h.ready();
  assert.equal((await h.saved()).draft.id,next.id);assert.equal(await h.cached(),next.id);assert(await h.page.locator('#send').isEnabled());
});
test('stale native window cannot overwrite a newer saved draft or replace its archive',async t=>{
  const h=await harness(t),initial=await h.open();const other=await h.context.newPage();await other.goto(origin);await h.ready(other);
  await other.locator('#description').fill('Second window owns the newer edit');
  await h.page.locator('#description').fill('Stale first-window edit');
  assert.equal((await h.saved()).draft.description,'Second window owns the newer edit');assert.equal(await h.cached(),initial.id);
  assert(await h.page.locator('#notice').evaluate(el=>el.classList.contains('error')));
  assert(await h.page.locator('#send').isDisabled());await h.transfer(report());
  assert.equal((await h.saved()).draft.id,initial.id);assert.equal(await h.cached(),initial.id);
});
test('interruption before draft save leaves the old archive authoritative over an orphan pending slot',async t=>{
  const h=await harness(t),initial=await h.open();await h.page.locator('#description').fill('Original edited draft survives');
  await h.page.evaluate(id=>new Promise(resolve=>{const r=indexedDB.open('kfps-private-report-logs-v1');r.onsuccess=()=>{const db=r.result,tx=db.transaction('bundle','readwrite'),s=tx.objectStore('bundle'),q=s.get('current');q.onsuccess=()=>s.put({...q.result,id,at:Date.now()},'pending');tx.oncomplete=()=>{db.close();resolve();};};}),crypto.randomUUID());
  await h.page.reload();await h.ready();assert.equal((await h.saved()).draft.id,initial.id);assert.equal(await h.cached(),initial.id);
  assert.equal(await h.page.locator('#description').inputValue(),'Original edited draft survives');assert(await h.page.locator('#send').isEnabled());
});
test('New report preserves a delivered receipt when saving the new identity fails',async t=>{
  const h=await harness(t),initial=await h.open();h.state.status='delivered';await h.page.locator('#send').click();
  await h.page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
  await h.page.evaluate(({key,id})=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage&&k===key&&JSON.parse(v).draft.id!==id)throw Error('Fixture quota exceeded');return original.call(this,k,v);};},{key:KEY,id:initial.id});
  await h.page.locator('#new-report').click();assert(await h.page.locator('#receipt').isVisible());
  assert.equal((await h.saved()).submitted.id,initial.id);assert.equal((await h.saved()).delivered_id,initial.id);
  assert(await h.page.locator('#notice').evaluate(el=>el.classList.contains('error')));assert.equal(h.posts.length,1);
});
test('blocked draft storage allows editing but cannot submit without a durable frozen receipt',async t=>{
  const h=await harness(t);await h.context.addInitScript(()=>{Storage.prototype.setItem=function(){throw Error('Fixture storage denied');};});
  await h.open();assert.match(await h.page.locator('#notice').textContent(),/cannot preserve the draft/i);
  assert(await h.page.locator('#send').isEnabled());await h.page.locator('#description').fill('Still usable without browser storage');
  h.state.status='delivered';await h.page.locator('#send').click();assert(await h.page.locator('#receipt').isHidden());assert.equal(h.posts.length,0);
  assert.match(await h.page.locator('#notice').textContent(),/cannot preserve the draft/i);
});
test('quota failure saving the frozen submission blocks POST and leaves a recoverable editable draft',async t=>{
  const h=await harness(t),initial=await h.open();h.state.postFailure=true;
  await h.page.locator('#description').fill('Preserve edits before any send attempt');
  await h.page.evaluate(key=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(this===localStorage&&k===key&&JSON.parse(v).submitted)throw Error('Fixture receipt quota exceeded');return original.call(this,k,v);};},KEY);
  await h.page.locator('#send').click();assert.equal(h.posts.length,0);assert(await h.page.locator('#receipt').isHidden());
  assert(await h.page.locator('#notice').evaluate(el=>el.classList.contains('error')));
  await h.page.reload();await h.ready();assert.equal((await h.saved()).draft.id,initial.id);assert.equal((await h.saved()).submitted,null);
  assert.equal(await h.page.locator('#description').inputValue(),'Preserve edits before any send attempt');
  h.state.postFailure=false;h.state.status='delivered';await h.page.locator('#send').click();await h.page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();assert.equal(h.posts.length,1);
});
test('browser sign-in cannot navigate away when saving edited draft fails',async t=>{
  const h=await harness(t,{native:false,authenticated:false});await h.open();
  await h.page.evaluate(key=>{const original=Storage.prototype.setItem;window.fixtureRestoreStorage=()=>{Storage.prototype.setItem=original;};Storage.prototype.setItem=function(k,v){if(this===sessionStorage&&k===key)throw Error('Fixture draft quota exceeded');return original.call(this,k,v);};},KEY);
  await h.page.locator('#description').fill('Unsaved edits must stay visible');let navigations=0;h.page.on('framenavigated',()=>navigations++);
  await h.page.locator('#login').click();await h.page.waitForTimeout(100);
  assert.equal(navigations,0);assert.equal(await h.page.locator('#description').inputValue(),'Unsaved edits must stay visible');
  assert(await h.page.locator('#notice').evaluate(el=>el.classList.contains('error')));assert.equal(h.posts.length,0);
  await h.page.evaluate(()=>fixtureRestoreStorage());await h.page.locator('#login').click();await h.ready();
  assert.equal(await h.page.locator('#description').inputValue(),'Unsaved edits must stay visible');assert.equal(h.posts.length,0);
});
test('sign-out revokes the session without reloading unsaved edits after a quota failure',async t=>{
  const h=await harness(t);await h.open();
  await h.page.evaluate(key=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k===key)throw Error('Fixture draft quota exceeded');return original.call(this,k,v);};},KEY);
  await h.page.locator('#description').fill('Unsaved text must survive sign-out');let navigations=0;h.page.on('framenavigated',()=>navigations++);
  await h.page.locator('#logout').click();await h.page.getByText('Not signed in',{exact:true}).waitFor();
  assert.equal(h.state.authenticated,false);assert.equal(navigations,0);
  assert.equal(await h.page.locator('#description').inputValue(),'Unsaved text must survive sign-out');
  assert.match(await h.page.locator('#notice').textContent(),/could not be saved/i);assert(await h.page.locator('#login').isVisible());assert.equal(h.posts.length,0);
});
test('delayed sign-out saves the latest edits before reload and stays open if that save fails',async t=>{
  const h=await harness(t);await h.open();let release,entered;
  const gate=new Promise(resolve=>{release=resolve;}),blocked=new Promise(resolve=>{entered=resolve;});
  await h.page.route('**/auth/logout',async route=>{entered();await gate;h.state.authenticated=false;await route.fulfill({json:{ok:true}});});
  let navigations=0;h.page.on('framenavigated',()=>navigations++);
  try {
    await h.page.locator('#logout').click();await blocked;
    await h.page.evaluate(key=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k===key)throw Error('Fixture late quota failure');return original.call(this,k,v);};},KEY);
    await h.page.locator('#description').fill('New edits made while sign-out was in progress');
    release();await h.page.getByText('Not signed in',{exact:true}).waitFor();
    assert.equal(h.state.authenticated,false);assert.equal(navigations,0);
    assert.equal(await h.page.locator('#description').inputValue(),'New edits made while sign-out was in progress');
    assert.match(await h.page.locator('#notice').textContent(),/could not be saved/i);assert.equal(h.posts.length,0);
  }finally{release();}
});
test('delivered marker accepts a later confirmed public link but cannot regress to retryable',async t=>{
  const h=await harness(t);await h.open();h.state.status='delivered';await h.page.locator('#send').click();await h.page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
  h.state.publicUrl='https://discord.com/channels/111111111111111111/222222222222222222';await h.page.reload();await h.ready();
  assert.equal(await h.page.locator('#post-link').getAttribute('href'),h.state.publicUrl);assert(await h.page.locator('#post-link').isVisible());
  h.state.status='retryable';await h.page.locator('#check').click();await h.page.waitForFunction(()=>!document.querySelector('#check').disabled);assert.equal(await h.page.locator('#result-title').textContent(),'Report sent');assert(await h.page.locator('#retry').isHidden());
  assert.equal(await h.page.locator('#post-link').getAttribute('href'),h.state.publicUrl);
  h.state.status='delivered';h.state.publicUrl='javascript:alert(1)';await h.page.locator('#check').click();await h.page.waitForFunction(()=>!document.querySelector('#check').disabled);
  assert.equal(await h.page.locator('#post-link').getAttribute('href'),'https://discord.com/channels/111111111111111111/222222222222222222');assert.equal(h.posts.length,1);
});
test('recovery choice renders without overflow in English and Korean at desktop and mobile sizes',async t=>{
  const h=await harness(t);await h.open();await h.transfer(report());
  for(const locale of ['en','ko'])for(const width of [1280,390]){
    await h.page.locator('#report-language').selectOption(locale);await h.page.setViewportSize({width,height:960});
    assert(await h.page.locator('#incoming-report').isVisible());assert(await h.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    for(const id of ['resume-report','replace-report'])assert(await h.page.locator('#'+id).evaluate(el=>el.scrollWidth<=el.clientWidth));
    const bytes=await h.page.screenshot({fullPage:true}),png=PNG.sync.read(bytes),colors=new Set();
    for(let i=0;i<png.data.length;i+=400)colors.add(png.data.subarray(i,i+3).toString('hex'));
    assert(colors.size>30,'rendered pixels must not be blank');
    if(output)fs.writeFileSync(path.join(output,`recovery-${locale}-${width}.png`),bytes);
  }
  assert.equal(h.posts.length,0);
});
