import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const catalogueQA=process.env.KFPS_GARAGE_CATALOGUE_QA==='1';
const qaName=process.env.KFPS_GARAGE_QA_NAME||'';
if(qaName&&!/^[a-z0-9][a-z0-9-]{0,79}$/.test(qaName))throw Error('Invalid QA run name');
const run=path.join(root,'tools/livery-studio/runs',qaName||(catalogueQA?'garage-catalogue-20261102':'garage-builds-20261102'));
const output=qaName?path.join(root,'runtime',qaName,'browser'):path.join(root,'runtime/garage-builds-20261102',catalogueQA?'cache-update/browser':'browser');
fs.mkdirSync(run,{recursive:true});fs.mkdirSync(output,{recursive:true});
fs.rmSync(path.join(run,'stop'),{force:true});
const require=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium}=require('playwright'),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const log=fs.openSync(path.join(output,'server.log'),'w');
const child=spawn(path.join(root,'python/python.exe'),['-I','-B',path.join(root,'tools/livery-studio/tests/garage-build-server.py')],
  {cwd:root,windowsHide:true,stdio:['ignore',log,log],env:{...process.env,TEMP:output,TMP:output}});
const errors=[],evidence={};let browser,page;
try {
  let info;
  for(let attempt=0;attempt<360;attempt++) {
    try{info=JSON.parse(fs.readFileSync(path.join(run,'browser-info.json'),'utf8'));}catch{}
    if(info?.pid===child.pid)break;
    assert.equal(child.exitCode,null,'Background server failed. See server.log.');await sleep(500);
  }
  assert.equal(info?.pid,child.pid,'Background server timed out.');
  const fixedStockQA=info.vehicle.car_id===2738;
  const alternateWing=fixedStockQA?2738001:344006;
  const restoreWing=fixedStockQA?2738001:344000;
  if(catalogueQA){
    assert.equal(info.partNames?.same_build_verified,true,'Installed catalogue was not used by preparation.');
    assert.equal(info.partNames?.provenance?.current,true);
    assert.match(info.partNames.source,/Installed cached/);
    evidence.partNames=info.partNames;
  }
  browser=await chromium.launch({headless:true,executablePath:process.env.KFPS_QA_BROWSER||'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-gpu-vsync'],env:{...process.env,TEMP:output,TMP:output}});
  const context=await browser.newContext({viewport:{width:1440,height:900}});
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(![info.preview,info.studio,info.switchStudio].filter(Boolean).map(value=>new URL(value).origin).includes(url.origin))return route.abort();
    if(!url.pathname.endsWith('/livery-scene.js'))return route.continue();
    const response=await route.fetch();
    return route.fulfill({response,body:await response.text()+`
      window.__garageScene={state:sceneState,metrics:sceneDiagnosticMetrics,frames:()=>renderedFrames,pixels(){
        renderer.render(scene,camera);const gl=renderer.getContext(),w=gl.drawingBufferWidth,h=gl.drawingBufferHeight;
        const data=new Uint8Array(w*h*4);gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,data);
        const bins=new Set();let hash=2166136261;for(let i=0;i<data.length;i+=16){bins.add([data[i]>>4,data[i+1]>>4,data[i+2]>>4].join(','));hash=Math.imul(hash^data[i],16777619);}
        return {width:w,height:h,colours:bins.size,hash:hash>>>0};}};`});
  });
  const selected=state=>Object.fromEntries(state.components.groups.map(group=>[group.part_type,group.selected]));
  const meshes=state=>state.components.meshes.filter(mesh=>mesh.visible).map(mesh=>mesh.name).sort();
  page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(info.preview);
  await page.waitForFunction(()=>window.__garageScene?.state().ready,null,{timeout:120000});
  const preview=await page.evaluate(()=>window.__garageScene.state());
  assert.deepEqual(selected(preview),info.build.parts);
  evidence.previewPixels=await page.evaluate(()=>window.__garageScene.pixels());
  assert(evidence.previewPixels.colours>20,'Preview is blank.');
  await page.screenshot({path:path.join(output,'preview-fitted.png')});
  evidence.preview={selected:selected(preview),meshes:meshes(preview),metrics:await page.evaluate(()=>window.__garageScene.metrics())};
  await page.close();
  page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(info.studio+'#layout='+info.handoff);
  await page.waitForFunction(()=>window.__liveryLab?.ready,null,{timeout:120000});
  assert.equal(new URL(page.url()).hash,'','Garage handoff was not adopted.');
  const studio=await page.evaluate(()=>window.__garageScene.state());
  assert.deepEqual(selected(studio),info.build.parts);
  assert.deepEqual(meshes(studio),evidence.preview.meshes,'Preview and Studio disagree about visible components.');
  evidence.studioPixels=await page.evaluate(()=>window.__garageScene.pixels());assert(evidence.studioPixels.colours>20);
  await page.click('[data-inspector-tab=car]');
  evidence.labels=await page.locator('#parts select').evaluateAll(nodes=>nodes.map(node=>({part:node.dataset.partType,text:node.selectedOptions[0]?.textContent})));
  if(fixedStockQA)assert(evidence.labels.filter(row=>['CarBody','Hood','RearBumper','SideSkirts'].includes(row.part)).every(row=>!row.text.includes('empty')));
  assert(evidence.labels.some(row=>row.text.includes('/')||!row.text.startsWith('Stock')&&!row.text.startsWith('Level')),'No source-derived product labels.');
  await page.screenshot({path:path.join(output,'studio-fitted.png')});
  const saved=await page.evaluate(()=>window.__liveryLab.getProject()),name='Garage body QA '+Date.now();
  await page.click('#saveProject');await page.fill('#layoutProjectName',name);await page.click('#saveLayoutProject [data-storage=save]');
  await page.waitForFunction(()=>!document.querySelector('#saveLayoutProject').open);
  await page.selectOption('#parts select[data-part-type=RearWing]',String(alternateWing));
  await page.waitForFunction(id=>window.__liveryLab.getScene().components.groups.find(group=>group.part_type==='RearWing').selected===id,alternateWing);
  const carbon=await page.evaluate(()=>window.__garageScene.state());
  if(!fixedStockQA){
  const carbonMeshes=carbon.components.meshes.filter(mesh=>mesh.visible&&mesh.name.startsWith('wing_e__'));
  assert(carbonMeshes.length>0,'The carbon wing did not become visible.');
  assert(carbonMeshes.every(mesh=>mesh.category!=='paint'&&mesh.category!=='glass'),'The carbon wing was made paintable.');
  const carbonLabel=await page.locator('#parts select[data-part-type=RearWing]').evaluate(node=>node.selectedOptions[0].textContent);
  assert.match(carbonLabel,/Big Country Labs/);
  evidence.carbonWing={label:carbonLabel,meshes:carbonMeshes,pixels:await page.evaluate(()=>window.__garageScene.pixels())};
  await page.screenshot({path:path.join(output,'studio-carbon-wing.png')});
  }
  await page.selectOption('#parts select[data-part-type=RearWing]',String(restoreWing));
  await page.waitForFunction(id=>window.__liveryLab.getScene().components.groups.find(group=>group.part_type==='RearWing').selected===id,restoreWing);
  const changed=await page.evaluate(()=>window.__liveryLab.getProject());
  evidence.stockWingPixels=await page.evaluate(()=>window.__garageScene.pixels());assert.notEqual(evidence.stockWingPixels.hash,evidence.studioPixels.hash);
  await page.evaluate(id=>{location.hash='#layout='+id;},info.invalid);
  await page.waitForFunction(()=>document.querySelector('#hostTransferMessage').textContent.includes('Unavailable Garage component'));
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),changed,'Invalid build changed the document.');
  await page.evaluate(id=>{location.hash='#layout='+id;},info.retry);
  await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
  assert.match(await page.locator('#confirmCarSwitch').innerText(),/fitted body/);
  await page.click('#confirmCarSwitch button[value=cancel]');
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),changed,'Cancellation changed the document.');
  page.on('dialog',dialog=>dialog.accept());
  await page.goto(info.studio);await page.waitForFunction(()=>window.__liveryLab?.ready,null,{timeout:120000});
  await page.click('#openProject');await page.selectOption('#openLayoutProject select',{label:name});await page.click('#openLayoutProject [data-storage=open]');
  await page.waitForFunction(id=>!document.querySelector('#openLayoutProject').open&&window.__liveryLab.getScene().components.groups.find(group=>group.part_type==='RearWing').selected===id,info.build.parts.RearWing);
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),saved,'Saved build did not survive reopening.');
  await page.setViewportSize({width:390,height:844});
  await page.click('[data-inspector-tab=car]');await page.screenshot({path:path.join(output,'narrow-fitted.png'),fullPage:true});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Narrow view overflow.');
  evidence.narrowPixels=await page.evaluate(()=>window.__garageScene.pixels());assert(evidence.narrowPixels.colours>20);
  await sleep(1000);const frames=await page.evaluate(()=>window.__garageScene.frames());await sleep(700);
  assert.equal(await page.evaluate(()=>window.__garageScene.frames()),frames,'Fitted build renders continuously while idle.');
  assert.deepEqual(errors,[]);
  evidence.errors=errors;evidence.idleFrames=frames;evidence.roundtrip=true;evidence.cancelRetained=true;
  if(info.switchStudio){
    await page.close();page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
    await page.addInitScript(()=>{window.__kfpsStudioNativeDownloads=true;});
    await page.goto(info.switchStudio);await page.waitForFunction(()=>window.__liveryLab?.ready,null,{timeout:120000});
    await page.click('[data-inspector-tab=car]');
    await page.selectOption('#parts select[data-part-type=RearWing]',String(alternateWing));
    const retained=await page.evaluate(()=>window.__liveryLab.getProject()),oldUrl=page.url();
    await page.evaluate(id=>{location.hash='#layout='+id;},info.switchInvalid);
    await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
    await page.click('#confirmCarSwitch button[value=discard]');
    await page.waitForFunction(()=>document.querySelector('#hostTransferMessage').textContent.includes('saved body parts could not be matched'),null,{timeout:60000});
    assert.equal(page.url().split('#')[0],oldUrl,'Invalid target rotated the session.');
    assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),retained,'Invalid cross-car build destroyed the document.');
    await page.screenshot({path:path.join(output,'cross-car-rejected.png')});
    await page.evaluate(id=>{location.hash='#layout='+id;},info.switchValid);
    await page.waitForFunction(()=>document.querySelector('#confirmCarSwitch').open);
    await page.click('#confirmCarSwitch button[value=discard]');
    await page.waitForFunction(id=>window.__liveryLab?.ready&&location.hash===''&&window.__liveryLab.getProject().vehicle.car_id===id,info.vehicle.car_id,{timeout:60000});
    assert.notEqual(page.url(),oldUrl,'Valid target did not replace the session.');
    assert.deepEqual(selected(await page.evaluate(()=>window.__garageScene.state())),info.build.parts);
    if(!fixedStockQA)assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject().vehicle_parts),info.build.parts);
    evidence.crossCar={invalidRetained:true,validAdopted:true,startingIdentity:'synthetic',targetGeometry:info.vehicle};
    await page.screenshot({path:path.join(output,'cross-car-adopted.png')});
    assert.deepEqual(errors,[]);
  }
  fs.writeFileSync(path.join(output,'evidence.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify({passed:true,preview:evidence.previewPixels,studio:evidence.studioPixels,labels:evidence.labels,errors},null,2));
} catch(error) {
  if(page&&!page.isClosed()){
    await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});
    fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({error:String(error),errors,text:await page.locator('body').innerText().catch(()=>''),log:fs.readFileSync(path.join(output,'server.log'),'utf8')},null,2));
  }
  throw error;
} finally {
  await browser?.close();fs.writeFileSync(path.join(run,'stop'),'stop');
  if(child.exitCode===null)await Promise.race([once(child,'exit'),sleep(10000)]);
  if(child.exitCode===null){const done=once(child,'exit');child.kill();await done;}
  fs.closeSync(log);
}
