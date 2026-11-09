import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const workspace=path.resolve(process.argv[2]||'');
assert(workspace.startsWith(path.join(root,'tools/livery-studio/runs')+path.sep),'Use an isolated Studio run directory.');
const output=path.join(workspace,'workspace-browser');fs.mkdirSync(output,{recursive:true});
const switchCar=process.argv[3]==='--switch';
const vehicle=switchCar?{car_id:344,model_code:'NIS_FairladyZ_03'}:{car_id:2574,model_code:'343_Warthog_15'};
const projectName=`Workspace QA ${Date.now()}`;
const require=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium}=require('playwright');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const log=fs.openSync(path.join(output,'server.log'),'w');
const started=performance.now();
const child=spawn(path.join(root,'python/python.exe'),['-B',path.join(root,'tools/livery-studio/tests/isolated_server.py'),
  '--kfps-root',root,'--game-root',process.env.KFPS_TEST_GAME_ROOT||'C:/XboxGames/Forza Horizon 6/Content',
  '--archive','343_Warthog_15.zip','--workspace',workspace],
  {cwd:root,windowsHide:true,stdio:['ignore',log,log],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',TEMP:output,TMP:output}});
let browser,page;const errors=[],requests=[],evidence={switchCar};let initialSceneRequests=0;
try{
  let info;
  for(let i=0;i<240;i++){
    try{info=JSON.parse(fs.readFileSync(path.join(workspace,'server-info.json'),'utf8'));}catch{}
    if(info?.pid===child.pid&&info.status==='running')break;
    assert(child.exitCode===null,'Studio server exited; inspect server.log.');await sleep(500);
  }
  assert(info?.pid===child.pid&&info.status==='running','Studio did not start.');
  evidence.backendMs=Math.round(performance.now()-started);
  const prepared=JSON.parse(fs.readFileSync(path.join(workspace,'prepared.json'),'utf8'));
  const shapes=Array.from({length:36},(_,i)=>({type:1048677,data:[(i%6-2.5)*38,(Math.floor(i/6)-2.5)*38,.3,.3,i*5,0,0],
    color:i%2?[255,30,125,255]:[40,220,170,255],mask:false}));
  const layout={format:'kfps-livery-layout-v1',vehicle,
    vinyls:prepared.editor_config.sections.map(s=>({id:'save-'+s.section,name:'Alignment '+s.section,shapes})),
    placements:prepared.editor_config.sections.map(s=>({
      id:'placement-'+s.section,vinylId:'save-'+s.section,section:s.section,x:0,y:0,scaleX:1,scaleY:1,rotation:0,opacity:1,visible:true}))};
  const id='9'.repeat(32),handoffs=path.join(workspace,'test-handoffs');fs.mkdirSync(handoffs,{recursive:true});
  fs.writeFileSync(path.join(handoffs,id+'.json'),JSON.stringify({format:'kfps-studio-host-layout-v1',created:Date.now()/1000,name:'Workspace QA',layout,
    ...(switchCar?{startup_session:info.url}:{})}));
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-gpu-vsync'],env:{...process.env,TEMP:output,TMP:output}});
  page=await browser.newPage({viewport:{width:1440,height:900}});
  if(switchCar)await page.addInitScript(()=>{window.__kfpsStudioNativeDownloads=true;});
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('request',request=>{
    requests.push(new URL(request.url()).pathname.replace(/\/[A-Za-z0-9_-]{43}\//,'/session/'));
    if(request.url()===info.url+'livery-scene.js')initialSceneRequests++;
  });
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!==new URL(info.url).origin)return route.abort();
    if(!url.pathname.endsWith('/livery-scene.js'))return route.continue();
    const response=await route.fetch();
    return route.fulfill({response,body:await response.text()+`
      window.__workspaceScene={pixels(){
        renderer.render(scene,camera);
        const gl=renderer.getContext(),w=gl.drawingBufferWidth,h=gl.drawingBufferHeight,pixels=new Uint8Array(w*h*4);
        gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
        const bins=new Set();let hash=2166136261;
        for(let i=0;i<pixels.length;i+=16){bins.add([pixels[i]>>4,pixels[i+1]>>4,pixels[i+2]>>4].join(','));hash=Math.imul(hash^pixels[i],16777619);}
        return {width:w,height:h,colours:bins.size,hash:hash>>>0};
      },frames:()=>renderedFrames,metrics:sceneDiagnosticMetrics};`});
  });
  const navStarted=performance.now();await page.goto(info.url+'#layout='+id,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__liveryLab?.ready||window.__liveryLabBootError,null,{timeout:120000});
  assert(await page.evaluate(()=>window.__liveryLab?.getProject().placements.length>0),'Package did not reach a usable document.');
  evidence.interactiveMs=Math.round(performance.now()-navStarted);
  assert.equal(new URL(page.url()).hash,'');
  if(switchCar)assert.equal(initialSceneRequests,0,'Wrong initial car renderer was imported before the package car.');
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),layout);
  assert.equal(await page.locator('[data-inspector-tab]').count(),5);
  evidence.canvas=await page.evaluate(()=>window.__workspaceScene.pixels());assert(evidence.canvas.colours>20,'Canvas is blank.');
  await page.screenshot({path:path.join(output,'desktop-placement.png')});
  for(const tab of ['design','car','view','project','placement']){
    await page.click(`[data-inspector-tab=${tab}]`);
    assert.equal(await page.locator('.inspector-panel:visible').count(),1);
    assert.equal(await page.locator(`#inspector-${tab}`).isVisible(),true);
  }
  await page.fill('#positionX','9000');await page.click('[data-inspector-tab=design]');
  assert.equal(await page.locator('#inspector-placement').isVisible(),true,'Invalid draft was hidden by a tab switch.');
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),layout);
  await page.fill('#positionX','23.5');await page.click('[data-inspector-tab=design]');
  assert.equal(await page.evaluate(()=>window.__liveryLab.getProject().placements[0].x),23.5);
  await page.click('[data-inspector-tab=placement]');await page.fill('#positionX','0');await page.click('[data-inspector-tab=design]');
  await page.click('[data-inspector-tab=car]');
  if(!switchCar){
    const downloading=page.waitForEvent('download');
    await page.click('#workspaceSearch');await page.fill('#workspaceCommandSearch input','Export section artwork');
    await page.locator('.commandSearchResult').click();
    const download=await downloading;await download.saveAs(path.join(output,'section-roundtrip.json'));
    await page.waitForFunction(()=>document.querySelector('#sectionExportStatus').textContent.includes('native shapes exported'));
    assert.equal(await page.locator('#inspector-design').isVisible(),true,'Command feedback remained in a hidden panel.');
    assert.equal(JSON.parse(fs.readFileSync(path.join(output,'section-roundtrip.json'),'utf8')).shapes.length,36);
  }
  await page.click('[data-quality-choice=fast]');
  await page.waitForFunction(()=>window.__liveryLab.getMetrics().previewQuality==='fast'&&!document.querySelector('#previewQuality').disabled);
  assert.equal(await page.locator('[data-quality-choice=fast]').getAttribute('aria-pressed'),'true');
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),layout,'Quality changed document data.');
  await page.click('[data-quality-choice=balanced]');
  await page.waitForFunction(()=>window.__liveryLab.getMetrics().previewQuality==='balanced'&&!document.querySelector('#previewQuality').disabled);
  const canvas=page.locator('#canvas'),box=await canvas.boundingBox();
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();
  await page.mouse.move(box.x+box.width*.7,box.y+box.height*.6,{steps:6});await page.mouse.up();await sleep(400);
  evidence.rotated=await page.evaluate(()=>window.__workspaceScene.pixels());assert.notEqual(evidence.canvas.hash,evidence.rotated.hash,'Orbit did not change the scene.');
  await page.click('[data-inspector-tab=car]');
  const part=page.locator('#parts select').first();
  if(await part.count())assert.equal(await part.isVisible(),true);
  if(switchCar){
    const wing=page.locator('#parts select[data-part-type=RearWing]');
    await wing.selectOption('344006');
    await page.waitForFunction(()=>window.__liveryLab.getProject().vehicle_parts?.RearWing===344006);
  }
  await page.screenshot({path:path.join(output,'desktop-car.png')});
  await page.click('#saveProject');await page.fill('#layoutProjectName',projectName);
  await page.click('#saveLayoutProject [data-storage=save]');await page.waitForFunction(()=>!document.querySelector('#saveLayoutProject').open);
  const saved=await page.evaluate(()=>window.__liveryLab.getProject());
  await page.reload({waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__liveryLab?.ready,null,{timeout:120000});
  assert.equal(await page.locator('[data-inspector-tab=car]').getAttribute('aria-selected'),'true');
  await page.click('#openProject');await page.selectOption('#openLayoutProject select',{label:projectName});
  await page.click('#openLayoutProject [data-storage=open]');
  await page.waitForFunction(()=>!document.querySelector('#openLayoutProject').open&&window.__liveryLab.getProject().placements.length>0);
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),saved,'Saved layout did not round-trip.');
  await page.setViewportSize({width:1100,height:760});await page.click('[data-inspector-tab=view]');
  await page.screenshot({path:path.join(output,'compact-view.png')});
  await page.setViewportSize({width:390,height:844});await page.click('[data-inspector-tab=project]');
  await page.screenshot({path:path.join(output,'narrow-project.png'),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Narrow layout overflows.');
  evidence.narrowCanvas=await page.evaluate(()=>window.__workspaceScene.pixels());assert(evidence.narrowCanvas.colours>20);
  await sleep(1200);const frames=await page.evaluate(()=>window.__workspaceScene.frames());await sleep(600);
  assert.equal(await page.evaluate(()=>window.__workspaceScene.frames()),frames,'Idle page continuously renders.');
  evidence.errors=errors;evidence.requests=requests;evidence.initialSceneRequests=initialSceneRequests;evidence.metrics=await page.evaluate(()=>window.__workspaceScene.metrics());
  assert.equal(requests.filter(value=>value.endsWith('/api/host-layout/'+id)).length,switchCar?2:1,'Startup fetched the same package again after preview initialization.');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(output,'evidence.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify({backendMs:evidence.backendMs,interactiveMs:evidence.interactiveMs,canvas:evidence.canvas,errors},null,2));
}catch(error){
  if(page){await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
    fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({error:String(error),errors,text:await page.locator('body').innerText().catch(()=>''),requests},null,2));}
  throw error;
}finally{
  await browser?.close();if(child.exitCode===null){const exited=once(child,'exit');child.kill();await exited;}fs.closeSync(log);
}
