const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {gzipSync}=require('node:zlib');

(async () => {
  const output = path.resolve(process.argv[2]);
  const {logBlob,logMetadata}=await import(pathToFileURL(path.join(__dirname,'log-fixture.mjs')));
  const {readSubmission}=await import(pathToFileURL(path.join(__dirname,'../src/submission.mjs')));
  fs.mkdirSync(output, {recursive:true});
  const files = new Set(fs.readdirSync(path.join(__dirname, '../public')));
  const server = http.createServer((req, res) => {
    const name = new URL(req.url, 'http://localhost').pathname.slice(1) || 'index.html';
    if (!files.has(name)) { res.writeHead(404); res.end(); return; }
    const type = name.endsWith('.html') ? 'text/html' : name.endsWith('.css') ? 'text/css' : name.endsWith('.png') ? 'image/png' : 'text/javascript';
    res.writeHead(200, {'Content-Type':type});
    res.end(fs.readFileSync(path.join(__dirname, '../public', name)));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({channel:'chrome', headless:true});
    const page = await browser.newPage({viewport:{width:1280,height:1000}}), posts = [], errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) { await route.abort(); return; }
      if (url.pathname === '/api/config') return route.fulfill({json:{enabled:true,join_url:'https://discord.gg/XT8dG8bDKy'}});
      if (url.pathname === '/api/session') return route.fulfill({json:{authenticated:true,name:'Synthetic Tester',csrf:'synthetic'}});
      if (url.pathname.startsWith('/api/reports')) {
        if (route.request().method() === 'POST') {
          const req=route.request(),accepted=await readSubmission(new Request(req.url(),{method:'POST',headers:req.headers(),body:req.postDataBuffer()}));
          assert.deepEqual(Buffer.from(await accepted.privateLogs.arrayBuffer()),Buffer.from(await logBlob.arrayBuffer()));
          posts.push(accepted.report);
        }
        return route.fulfill({json:{id:draft.id,status:'delivered',message:'Synthetic delivery only.',public_url:null}});
      }
      await route.continue();
    });
    const draft = {schema:'kfps-support-report/1', id:crypto.randomUUID(), feature:'Editor', source:'kfps', description:'Synthetic test: shape movement stalls.', technical:{app:{version:'3.1.76'},
      editor:{schema:'kfps-editor-diagnostics/1',page:{page:'a'.repeat(32),seq:1,state:{layers:355,referenceWidth:1216,referenceHeight:832},metrics:{frameMax:280},events:[{kind:'long-task',action:'rotate',duration:280}]},recent:[]},
      logs:Array.from({length:10},(_,i)=>({source:i ? `worker-${i}` : 'editor-desktop',text:`Error: synthetic worker ${i}\nsession_token=PRIVATE_TEST`,age_seconds:20,previous_session:true}))}};
    draft.private_logs=logMetadata;
    const prepared=gzipSync(JSON.stringify({schema:'kfps-support-package/1',report:draft,logs_base64:Buffer.from(await logBlob.arrayBuffer()).toString('base64')}));
    await page.goto(origin + '/#bundle=' + prepared.toString('base64url'));
    await page.locator('#description').waitFor();
    await page.waitForFunction(() => !!document.getElementById('technical').textContent);
    await page.getByText('Review technical details', {exact:true}).click();
    const reviewed = JSON.parse(await page.locator('#technical').textContent());
    assert.equal(reviewed.logs.length, 10);
    assert.equal(reviewed.editor.page.metrics.frameMax, 280);
    assert.equal(reviewed.editor.page.state.layers, 355);
    assert.equal(JSON.stringify(reviewed).includes('PRIVATE_TEST'), false);
    assert.equal(posts.length, 0);
    for (const [width,height] of [[1280,1000],[390,844]]) {
      await page.setViewportSize({width,height});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({path:path.join(output, `review-${width}.png`),fullPage:true});
    }
    await page.setViewportSize({width:1280,height:1000});
    await page.getByRole('button',{name:'Send report',exact:true}).click();
    await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    assert.equal(posts.length, 1);
    assert.deepEqual(posts[0].technical.editor, reviewed.editor);
    assert.deepEqual(posts[0].technical.logs, reviewed.logs);
    await page.reload();
    await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    assert.equal(posts.length, 1);
    assert.deepEqual(errors, []);
    const results = {passed:true, sources:10, editorDiagnosticsPreserved:true, noAutomaticSubmission:true, redaction:true, widths:[1280,390], realDiscordPosts:0};
    fs.writeFileSync(path.join(output,'results.json'), JSON.stringify(results,null,2));
    console.log(JSON.stringify(results));
  } finally { if (browser) await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => {console.error(error); process.exitCode=1;});
