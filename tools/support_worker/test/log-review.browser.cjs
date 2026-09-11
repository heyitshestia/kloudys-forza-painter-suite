const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {chromium} = require('playwright');
const assert = require('node:assert/strict');

(async () => {
  const output = path.resolve(process.argv[2]);
  fs.mkdirSync(output, {recursive:true});
  const files = new Set(['index.html', 'form.js', 'protocol.mjs', 'editor-diagnostics.mjs', 'style.css', 'kfps-logo.png']);
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
        if (route.request().method() === 'POST') posts.push(route.request().postDataJSON());
        return route.fulfill({json:{id:draft.id,status:'delivered',message:'Synthetic delivery only.',public_url:null}});
      }
      await route.continue();
    });
    const draft = {schema:'kfps-support-report/1', id:crypto.randomUUID(), feature:'Editor', source:'kfps', description:'Synthetic test: shape movement stalls.', technical:{app:{version:'3.1.76'},
      editor:{schema:'kfps-editor-diagnostics/1',page:{page:'a'.repeat(32),seq:1,state:{layers:355,referenceWidth:1216,referenceHeight:832},metrics:{frameMax:280},events:[{kind:'long-task',action:'rotate',duration:280}]},recent:[]},
      logs:Array.from({length:10},(_,i)=>({source:i ? `worker-${i}` : 'editor-desktop',text:`Error: synthetic worker ${i}\nsession_token=PRIVATE_TEST`,age_seconds:20,previous_session:true}))}};
    await page.goto(origin + '/#draft=' + Buffer.from(JSON.stringify(draft)).toString('base64url'));
    await page.locator('#description').waitFor();
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
