import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const run=path.join(root,'tools/livery-studio/runs/garage-workflow-20261104/browser');
const output=path.join(root,'runtime/garage-workflow-20261104/studio-browser');
fs.mkdirSync(run,{recursive:true});fs.mkdirSync(output,{recursive:true});
fs.rmSync(path.join(run,'stop'),{force:true});
const require=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium}=require('playwright'),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const log=fs.openSync(path.join(output,'server.log'),'w');
const child=spawn(path.join(root,'python/python.exe'),['-I','-B',path.join(root,'tools/livery-studio/tests/garage-workflow-server.py')],
  {cwd:root,windowsHide:true,stdio:['ignore',log,log],env:{...process.env,TEMP:output,TMP:output}});
const errors=[],evidence={};let browser,page;
try {
  let info;
  for(let attempt=0;attempt<120;attempt++) {
    try{info=JSON.parse(fs.readFileSync(path.join(run,'browser-info.json'),'utf8'));}catch{}
    if(info?.pid===child.pid)break;
    assert.equal(child.exitCode,null,'Server failed. See server.log.');await sleep(500);
  }
  assert.equal(info?.pid,child.pid,'Server timed out.');
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-gpu-vsync'],env:{...process.env,TEMP:output,TMP:output}});
  const context=await browser.newContext({viewport:{width:1440,height:900}});
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(![info.url,info.switchUrl].map(value=>new URL(value).origin).includes(url.origin))return route.abort();
    if(!url.pathname.endsWith('/livery-scene.js'))return route.continue();
    const response=await route.fetch();
    await route.fulfill({response,body:await response.text()+`
      window.__workflowScene={state:sceneState,frames:()=>renderedFrames,pixels(){
        renderer.render(scene,camera);const gl=renderer.getContext(),w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;
        const data=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,data);
        const bins=new Set();for(let i=0;i<data.length;i+=16)bins.add([data[i]>>4,data[i+1]>>4,data[i+2]>>4].join(','));
        return {width:w,height:h,colours:bins.size};}};`});
  });
  page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  const handoff=async(kind,key)=>{
    await page.evaluate(({kind,id})=>{location.hash='#'+kind+'='+id;},{kind,id:info.handoffs[key]});
  };
  const adopted=()=>page.waitForFunction(()=>!location.hash);
  const document=()=>page.evaluate(()=>window.__liveryLab.getProject());
  const selected=()=>page.evaluate(()=>Object.fromEntries(window.__workflowScene.state().components.groups.map(g=>[g.part_type,g.selected])));
  await page.goto(info.url+'#project='+info.handoffs.linked);
  await page.waitForFunction(()=>window.__liveryLab?.ready,null,{timeout:120000});await adopted();
  const linked=await document();
  assert.deepEqual(linked.authoring,info.project.authoring);
  assert.deepEqual(linked.vinyls,info.project.vinyls);
  assert.deepEqual(linked.placements,info.project.placements);
  assert.deepEqual(await selected(),info.build.parts);
  evidence.linked={authoring:true,groups:true,parts:true};
  console.log('Linked project adoption verified');
  await page.screenshot({path:path.join(output,'linked-project.png')});
  await handoff('project','stock');await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
  await page.click('#confirmCarSwitch button[value=cancel]');assert.deepEqual(await document(),linked);
  await page.click('#retryHostTransfer');await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
  await page.click('#confirmCarSwitch button[value=save]');await page.waitForFunction(()=>document.querySelector('#saveLayoutProject').open);
  await page.click('#saveLayoutProject [data-storage=cancel-save]');assert.deepEqual(await document(),linked);
  await page.click('#retryHostTransfer');await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
  await page.click('#confirmCarSwitch button[value=save]');await page.waitForFunction(()=>document.querySelector('#saveLayoutProject').open);
  await page.fill('#layoutProjectName','Linked workflow '+Date.now());await page.click('#saveLayoutProject [data-storage=save]');await adopted();
  const stock=await document();assert.equal(stock.placements.length,0);assert.equal(stock.vinyls.length,0);assert.equal(stock.vehicle_parts,undefined);
  const stockParts=await selected();assert.notDeepEqual(stockParts,info.build.parts);
  assert(await page.evaluate(()=>window.__workflowScene.state().components.groups.every(group=>group.selected===null||group.options.some(option=>option.id===group.selected&&option.stock))), 'Blank project did not reset to true stock components');
  const reopened=await page.evaluate(async()=>{const entries=await fetch('./api/projects').then(r=>r.json());return fetch('./api/projects/'+entries.entries[0].id).then(r=>r.json());});
  assert.deepEqual(reopened.project,linked);evidence.saveReopen=true;
  evidence.stock={blank:true,parts:stockParts};
  console.log('Unsaved protections and stock components verified');
  await handoff('layout','artwork');
  await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
  await page.click('#confirmCarSwitch button[value=discard]');
  await adopted();
  const artwork=await document();assert.deepEqual(artwork.vinyls,info.artwork.vinyls);assert.deepEqual(await selected(),info.build.parts);
  evidence.artwork={groups:true,currentBuild:true};
  console.log('Current build and artwork verified');
  await handoff('project','invalid');await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
  await page.click('#confirmCarSwitch button[value=discard]');
  await page.waitForFunction(()=>document.querySelector('#hostTransferMessage').classList.contains('error'));
  assert.deepEqual(await document(),artwork);
  evidence.invalidRetained=true;evidence.unsaved={cancel:true,cancelSave:true,save:true};
  evidence.desktopPixels=await page.evaluate(()=>window.__workflowScene.pixels());assert(evidence.desktopPixels.colours>20);
  await page.screenshot({path:path.join(output,'current-build-artwork.png')});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(output,'narrow-artwork.png'),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  evidence.mobilePixels=await page.evaluate(()=>window.__workflowScene.pixels());assert(evidence.mobilePixels.colours>20);
  await sleep(1000);const frames=await page.evaluate(()=>window.__workflowScene.frames());await sleep(700);
  assert.equal(await page.evaluate(()=>window.__workflowScene.frames()),frames);evidence.idle=true;
  await page.close();page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  await page.addInitScript(()=>{window.__kfpsStudioNativeDownloads=true;});
  await page.goto(info.switchUrl);
  await page.waitForFunction(()=>window.__liveryLab?.ready,null,{timeout:60000});
  await page.click('[data-inspector-tab=car]');
  await page.selectOption('#parts select[data-part-type=RearWing]','344006');
  const previous=await document();
  await handoff('project','switchInvalid');await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
  await page.click('#confirmCarSwitch button[value=discard]');
  await page.waitForFunction(()=>document.querySelector('#hostTransferMessage').classList.contains('error'),null,{timeout:60000});
  assert.equal(page.url().split('#')[0],info.switchUrl);assert.deepEqual(await document(),previous);
  await page.click('#cancelCarSwitch');await page.waitForFunction(()=>document.querySelector('#cancelCarSwitch').textContent==='Close');
  await page.click('#cancelCarSwitch');await page.waitForFunction(()=>!document.querySelector('#carPicker').open);
  evidence.invalidCrossCarRetained=true;
  await handoff('project','switch');await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
  await page.click('#confirmCarSwitch button[value=discard]');
  await page.waitForFunction(()=>window.__liveryLab?.ready&&!location.hash,null,{timeout:60000});
  assert.notEqual(page.url(),info.switchUrl);assert.deepEqual((await document()).authoring,info.project.authoring);
  assert.deepEqual(await selected(),info.build.parts);evidence.nativeSwitch=true;
  assert.deepEqual(errors,[]);evidence.errors=errors;
  fs.writeFileSync(path.join(output,'evidence.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify(evidence));
}catch(error){
  if(page&&!page.isClosed()){
    await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
    fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({error:String(error),errors,
      status:await page.locator('#hostTransferMessage').textContent().catch(()=>''),evidence},null,2));
  }
  throw error;
}finally{
  await browser?.close();fs.writeFileSync(path.join(run,'stop'),'stop');
  for(let attempt=0;attempt<100&&child.exitCode===null;attempt++)await sleep(100);
  if(child.exitCode===null){child.kill();throw Error('Server did not stop normally.');}
  fs.closeSync(log);
}
