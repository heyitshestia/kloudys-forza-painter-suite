const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');

(async()=>{
  const output=path.resolve(process.argv[2]);fs.mkdirSync(output,{recursive:true});
  const {readSubmission}=await import(pathToFileURL(path.join(__dirname,'../src/submission.mjs')));
  const publicRoot=path.join(__dirname,'../public'),allowed=new Set(fs.readdirSync(publicRoot));
  const server=http.createServer((req,res)=>{
    const name=new URL(req.url,'http://localhost').pathname.slice(1)||'index.html';
    if(!allowed.has(name)){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'Content-Type':name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':name.endsWith('.png')?'image/png':'text/javascript'});
    res.end(fs.readFileSync(path.join(publicRoot,name)));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin=`http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser=await chromium.launch({channel:'chrome',headless:true});
    const page=await browser.newPage({viewport:{width:1280,height:960}}),errors=[],posts=[],checks=[];
    const check=(ok,name)=>{assert.ok(ok,name);checks.push(name);};
    page.on('pageerror',error=>errors.push(String(error)));
    await page.setContent('<html><body style="margin:0;background:#eef4f5;color:#183b44;font:24px Arial;padding:48px"><h1>KFPS reporting test</h1><p>Synthetic screenshot. No real project or personal information.</p><div style="width:480px;height:210px;background:#327b83;color:white;padding:24px">Public screenshot delivery verification</div></body></html>');
    const png=await page.screenshot({path:path.join(output,'synthetic-screenshot.png')});
    const jpeg=await page.screenshot({type:'jpeg',path:path.join(output,'synthetic-screenshot.jpg')});
    const images=[{name:'PRIVATE-original-name.png',mimeType:'image/png',buffer:png},{name:'PRIVATE-original-name.jpg',mimeType:'image/jpeg',buffer:jpeg}];
    let authenticated=false,status='retryable';
    await page.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url());
      if(url.origin!==origin)return route.abort();
      if(url.pathname==='/api/config')return route.fulfill({json:{enabled:true,join_url:'https://discord.gg/XT8dG8bDKy'}});
      if(url.pathname==='/api/session')return route.fulfill({json:{authenticated,name:'Synthetic Tester',csrf:'synthetic'}});
      if(url.pathname.startsWith('/api/reports')) {
        if(req.method()==='POST') {
          const result=await readSubmission(new Request(req.url(),{method:'POST',headers:req.headers(),body:req.postDataBuffer()}));
          posts.push(result);status=posts.length===1?'retryable':'delivered';
        }
        return route.fulfill({json:{status,message:'Synthetic local verification only.',retry_after:0,public_url:null}});
      }
      return route.continue();
    });
    await page.goto(origin);
    await page.getByText('Sign in to send',{exact:true}).waitFor();
    check(await page.locator('#screenshots').isDisabled(),'screenshots require sign-in first');
    authenticated=true;await page.reload();await page.getByText('Signed in as Synthetic Tester',{exact:true}).waitFor();
    await page.locator('#description').fill('Synthetic screenshot workflow verification.');
    await page.locator('#title').fill('Screenshot browser test');
    await page.context().grantPermissions(['clipboard-read','clipboard-write'],{origin});
    await page.evaluate(async base64=>{
      const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
      await navigator.clipboard.write([new ClipboardItem({'image/png':new Blob([bytes],{type:'image/png'})})]);
    },png.toString('base64'));
    await page.locator('#description').press('Control+V');
    await page.locator('#screenshot-previews img').waitFor();
    check(await page.locator('#screenshot-previews img').count()===1,'clipboard screenshot paste is previewed, not submitted');
    await page.getByRole('button',{name:'Remove screenshot 1',exact:true}).click();
    await page.locator('#screenshots').setInputFiles(images);
    await page.locator('#screenshot-previews img').nth(1).waitFor();
    check(await page.locator('#screenshot-previews img').count()===2,'PNG and JPEG previews are shown');
    check(await page.locator('#screenshot-warning').isVisible(),'public visibility warning is displayed');
    await page.locator('#send').click();
    check((await page.locator('#notice').innerText()).includes('Confirm'),'public consent is mandatory');
    check(posts.length===0,'missing consent sends nothing');
    await page.locator('#screenshots-public').check();
    await page.getByRole('button',{name:'Remove screenshot 2',exact:true}).click();
    check(!await page.locator('#screenshots-public').isChecked(),'changing selected screenshots resets consent');
    await page.locator('#screenshots').setInputFiles({name:'bad.svg',mimeType:'image/svg+xml',buffer:Buffer.from('<svg></svg>')});
    await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('valid PNG'));
    check(await page.locator('#screenshot-previews img').count()===1,'invalid image leaves valid selection intact');
    await page.locator('#screenshots').setInputFiles([images[0],images[0],images[0]]);
    await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('no more than 3'));
    check(await page.locator('#screenshot-previews img').count()===1,'excess image count is rejected atomically');
    await page.locator('#screenshots').setInputFiles(images[1]);
    await page.locator('#screenshot-previews img').nth(1).waitFor();
    await page.locator('#screenshots-public').check();
    await page.locator('#include').uncheck();
    for(const [width,height] of [[1280,960],[390,844]]) {
      await page.setViewportSize({width,height});
      check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`no overflow at ${width}`);
      check(await page.locator('#screenshot-previews img').evaluateAll(imgs=>imgs.every(img=>img.complete&&img.naturalWidth>0)),`image pixels decoded at ${width}`);
      await page.screenshot({path:path.join(output,`screenshots-${width}.png`),fullPage:true});
    }
    await page.locator('#send').click();
    await page.locator('#retry').waitFor({state:'visible'});
    check(posts.length===1,'first submission reaches actual multipart parser');
    check(posts[0].files.length===2&&Object.keys(posts[0].report.technical).length===0,'screenshots still sent when private diagnostics excluded');
    check(!JSON.stringify(posts[0].report).includes('PRIVATE-original'),'original filenames excluded from report');
    await page.reload();await page.locator('#retry').waitFor({state:'visible'});
    check((await page.locator('#screenshot-state').innerText()).includes('reattach'),'reload explains how to retry missing screenshots');
    await page.locator('#retry').click();
    check(posts.length===1,'missing screenshots never silently resubmit');
    await page.locator('#check').click();await page.locator('#retry').waitFor({state:'visible'});
    await page.locator('#screenshots').setInputFiles(images);await page.locator('#screenshot-previews img').nth(1).waitFor();
    await page.locator('#retry').click();await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    check(posts.length===2,'retry with identical screenshots succeeds');
    check((await page.locator('#notice').innerText())==='','successful delivery clears stale progress notices');
    check(JSON.stringify(posts[0].report)===JSON.stringify(posts[1].report),'retry retains exact report hash inputs');
    for(let i=0;i<2;i++)assert.deepEqual(Buffer.from(await posts[0].files[i].arrayBuffer()),Buffer.from(await posts[1].files[i].arrayBuffer()));
    await page.reload();await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    check(posts.length===2,'delivered receipt reload does not submit again');
    check(errors.length===0,'no browser errors');
    const results={passed:true,checks,realDiscordPosts:0,errors};
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
  } finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
