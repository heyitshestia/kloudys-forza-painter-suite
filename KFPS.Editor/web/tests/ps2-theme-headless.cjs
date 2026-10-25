'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const readline = require('node:readline');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../../..');
const output = path.join(root, 'KFPS.Editor/runtime', process.env.KFPS_PS2_RUN || 'ps2-headless-20261025');
assert.ok(path.basename(output).match(/^ps2-headless-[a-z0-9-]+$/));
fs.mkdirSync(output, {recursive:true});
const report = {checks:[],limitations:['Studio theme UI/API only; car renderer is not part of this fixture.']};
const log = fs.createWriteStream(path.join(output,'server.log'));
let host, browser;
async function startHost() {
  const child = cp.spawn(process.env.KFPS_TEST_PYTHON, ['-B',path.join(__dirname,'xbox-theme-server.py'),output], {cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe']});
  child.stderr.pipe(log,{end:false});
  const done = new Promise(resolve=>child.once('exit',resolve));
  const info = await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{child.kill();reject(Error('Host startup timed out'));},20000);
    readline.createInterface({input:child.stdout}).once('line',line=>{clearTimeout(timer);try{resolve(JSON.parse(line));}catch(error){reject(error);}});
    child.once('error',reject);child.once('exit',code=>{clearTimeout(timer);reject(Error('Host exited '+code));});
  });
  return {...info,stop:async()=>{child.stdin.end('\n');assert.equal(await done,0);}};
}
async function openPages(context) {
  const editor=await context.newPage();
  const errors=[];editor.on('pageerror',error=>errors.push(error.message));
  await editor.addInitScript(()=>localStorage.setItem('kloudyFabricStartupHelpConfirmed','true'));
  await editor.goto(host.editor);await editor.waitForFunction(()=>window.KfpsDesktop?.ready);
  await editor.evaluate(async()=>{await KfpsEditorPreferences.ready;await editorTheme.loadEditorThemes();await editorTheme.loadEditorThemePreference();document.querySelectorAll('dialog[open]').forEach(d=>d.close());});
  const studio=await context.newPage();studio.on('pageerror',error=>errors.push(error.message));
  const source=fs.readFileSync(path.join(root,'tools/livery-studio/src/web/livery-editor.mjs'),'utf8');
  await studio.route('**/livery-editor.mjs',route=>route.fulfill({contentType:'text/javascript',body:source.slice(source.indexOf('function icon(button)'),source.indexOf('async function responseError'))}));
  await studio.goto(host.studio);await studio.waitForFunction(()=>!document.querySelector('#showTheme').disabled);
  return {editor,studio,errors};
}
async function select(page,id,studio=false) {
  await page.locator(studio?'#showTheme':'#workspaceViewMenu').click();
  await page.locator(studio?'#themeChoice':'#editorThemeSelect').selectOption(id);
  if(studio) {await page.locator('#applyTheme').click();await page.locator('#themeDialog').waitFor({state:'hidden'});}
  else {await page.keyboard.press('Escape');await page.evaluate(()=>KfpsEditorPreferences.flush());}
}
async function adjust(page,studio=false) {
  if(studio)await page.locator('#showTheme').click();
  else {await page.locator('#workspaceViewMenu').click();await page.locator('#adjustTheme').click();}
  await page.locator(studio?'#themeDialog':'#themeAdjustDialog').waitFor({state:'visible'});
  await page.waitForTimeout(220);
}
async function state(page) {return page.evaluate(()=>({base:document.documentElement.dataset.editorThemeBase,accent:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()}));}
async function geometry(page,studio=false) {return page.locator(studio?'#workspace,#viewport,#library,#authoring':'.workspace,.canvasStage,.rightDock,.toolRail').evaluateAll(nodes=>nodes.map(n=>{const r=n.getBoundingClientRect();return [r.x,r.y,r.width,r.height];}));}
async function cancel(page,studio=false) {await page.locator(studio?'#themeCancel':'#closeThemeAdjust').click();}
async function motion(page,studio=false) {
  await page.emulateMedia({reducedMotion:'no-preference'});
  const data=await page.evaluate(studio=>{
    document.querySelector(studio?'#showTheme':'#workspaceViewMenu').click();
    const n=document.querySelector(studio?'#themeDialog':'.workspaceMenu:popover-open');getComputedStyle(n).opacity;
    const a=n.getAnimations().find(a=>a.animationName==='ps2ChromeEnter');
    if(!a)throw Error('Missing PS2 entrance');a.pause();a.currentTime=70;
    const opacity=getComputedStyle(n).opacity;
    Object.defineProperty(document,'hasFocus',{configurable:true,value:()=>false});window.dispatchEvent(new Event('blur'));
    return {opacity:Number(opacity),settled:getComputedStyle(n).opacity,gate:document.documentElement.dataset.ps2Motion};
  },studio);
  assert.ok(data.opacity>.4&&data.opacity<1);assert.equal(data.settled,'1');assert.equal(data.gate,'paused');
  if(studio)await cancel(page,true);else await page.keyboard.press('Escape');
  await page.evaluate(()=>{delete document.hasFocus;window.dispatchEvent(new Event('focus'));});
  await page.emulateMedia({reducedMotion:'reduce'});await adjust(page,studio);
  assert.equal(await page.locator(studio?'#themeDialog':'#themeAdjustDialog').evaluate(n=>getComputedStyle(n).animationName),'none');
  await cancel(page,studio);await page.emulateMedia({reducedMotion:'no-preference'});
  return data;
}
(async()=>{
  host=await startHost();browser=await chromium.launch({channel:'chrome',headless:true,args:['--disable-background-networking','--disable-gpu']});
  let context=await browser.newContext({viewport:{width:1600,height:1000}});
  await context.route(/^https?:\/\/(?!127\.0\.0\.1[:/])/,route=>route.abort());
  let pages=await openPages(context);
  const artwork=await pages.editor.evaluate(async()=>{
    await loadPayload({shapes:Array.from({length:300},(_,i)=>({type:1048677+i%3,color:[80+i%175,110,160,255],data:[(i%20)*45-450,Math.floor(i/20)*45-300,.2,.2,i*3,0,0]}))});
    return JSON.stringify(vinylObjects().map(o=>o.toObject()));
  });
  for(const [name,page,studio] of [['editor',pages.editor,false],['studio',pages.studio,true]]) {
    const bounds=await geometry(page,studio);
    for(const id of ['pastel','dark','blackout','whiteout','builtin:xbox']) {
      await select(page,id,studio);const before=await state(page);
      await select(page,'builtin:ps2',studio);assert.equal((await state(page)).accent,'#7ba9ff');
      assert.deepEqual(await geometry(page,studio),bounds);
      await select(page,id,studio);assert.deepEqual(await state(page),before);
    }
    await select(page,'builtin:ps2',studio);
    report[name+'Motion']=await motion(page,studio);
    await page.screenshot({path:path.join(output,name+'-ps2.png')});
    await adjust(page,studio);await page.locator('[data-theme-var="--accent"]').fill('invalid-color');
    assert.ok(await page.locator(studio?'#applyTheme':'#saveThemeAdjust').isDisabled());
    await cancel(page,studio);assert.equal((await state(page)).accent,'#7ba9ff');
    await adjust(page,studio);await page.locator('[data-theme-var="--accent"]').fill('#ffd177');
    await cancel(page,studio);assert.equal((await state(page)).accent,'#7ba9ff');
    await adjust(page,studio);await page.locator(studio?'#themeName':'#themeAdjustName').fill('PS2 custom test');
    await page.locator('[data-theme-var="--accent"]').fill('#ffd177');
    if(studio) {
      const promise=page.waitForEvent('download');await page.locator('#downloadTheme').click();
      const download=await promise;await download.saveAs(path.join(output,'studio-custom.json'));
    }
    await page.locator(studio?'#applyTheme':'#saveThemeAdjust').click();
    await page.locator(studio?'#themeDialog':'#themeAdjustDialog').waitFor({state:'hidden'});
    if(!studio)await page.evaluate(()=>KfpsEditorPreferences.flush());
    assert.deepEqual(await state(page),{base:'builtin:ps2',accent:'#ffd177'});
    for(const size of [{width:1600,height:1000},{width:900,height:700}]) {
      await page.setViewportSize(size);await adjust(page,studio);
      assert.ok(await page.locator(studio?'#themeDialog':'#themeAdjustDialog').evaluate(n=>{const r=n.getBoundingClientRect();return r.left>=0&&r.top>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1;}));
      await page.screenshot({path:path.join(output,name+'-dialog-'+size.width+'.png')});
      await cancel(page,studio);
    }
    report.checks.push(name+': five prior themes, unchanged geometry, motion/reduced motion, invalid-color guard, cancel/save, compact dialogs');
  }
  assert.equal(await pages.editor.evaluate(()=>JSON.stringify(vinylObjects().map(o=>o.toObject()))),artwork);
  const colors=await pages.editor.evaluate(()=>{
    const n=canvas.lowerCanvasEl,data=n.getContext('2d').getImageData(0,0,n.width,n.height).data,s=new Set();
    for(let i=0;i<data.length;i+=400)s.add(data.slice(i,i+3).join(','));return s.size;
  });assert.ok(colors>20);report.canvasSampleColors=colors;
  assert.deepEqual(pages.errors,[]);
  await context.close();await host.stop();host=null;
  host=await startHost();context=await browser.newContext({viewport:{width:1600,height:1000}});
  await context.route(/^https?:\/\/(?!127\.0\.0\.1[:/])/,route=>route.abort());
  pages=await openPages(context);
  for(const page of [pages.editor,pages.studio])assert.deepEqual(await state(page),{base:'builtin:ps2',accent:'#ffd177'});
  await select(pages.studio,'whiteout',true);await adjust(pages.studio,true);
  await pages.studio.locator('#themeFile').setInputFiles(path.join(output,'studio-custom.json'));
  await pages.studio.locator('#applyTheme').click();await pages.studio.locator('#themeDialog').waitFor({state:'hidden'});
  assert.deepEqual(await state(pages.studio),{base:'builtin:ps2',accent:'#ffd177'});
  await select(pages.studio,'host',true);assert.equal((await state(pages.studio)).base,'dark');
  await select(pages.editor,'pastel');
  assert.deepEqual(pages.errors,[]);
  report.checks.push('Fresh host processes and empty browser storage restore both custom themes; Studio file round trip and return to host/default');
  report.checks.push('300-shape artwork identical before/after all theme edits; canvas pixels nonblank');
  report.passed=true;
})().catch(error=>{report.passed=false;report.error=error.stack;process.exitCode=1;console.error(error);}).finally(async()=>{
  if(!report.passed&&browser)for(const [i,page] of browser.contexts().flatMap(c=>c.pages()).entries())await page.screenshot({path:path.join(output,'failure-'+i+'.png')}).catch(()=>{});
  if(browser)await browser.close();if(host)await host.stop();log.end();
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
});
