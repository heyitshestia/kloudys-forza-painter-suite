import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const workspace=path.resolve(process.argv[2]||'');
assert(workspace.startsWith(path.join(root,'tools/livery-studio/runs')+path.sep));
const output=path.join(workspace,'browser');fs.mkdirSync(output,{recursive:true});
const require=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium}=require('playwright'),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const log=fs.openSync(path.join(output,'server.log'),'w');
const child=spawn(path.join(root,'python/python.exe'),['-B',path.join(root,'tools/livery-studio/tests/isolated_server.py'),
  '--kfps-root',root,'--game-root',process.env.KFPS_TEST_GAME_ROOT||'E:/SteamLibrary/steamapps/common/ForzaHorizon6',
  '--archive','nis_gtrlm_95.zip','--workspace',workspace],
  {cwd:root,windowsHide:true,stdio:['ignore',log,log],env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',TEMP:output,TMP:output}});
let browser,page;const errors=[],checks=[],evidence={};
try{
  let info;
  for(let i=0;i<240;i++){
    try{info=JSON.parse(fs.readFileSync(path.join(workspace,'server-info.json'),'utf8'));}catch{}
    if(info?.pid===child.pid&&info.status==='running')break;
    assert(child.exitCode===null,'Test backend exited; inspect server.log.');await sleep(500);
  }
  assert(info?.pid===child.pid&&info.status==='running','Test backend did not start.');
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-gpu-vsync'],env:{...process.env,TEMP:output,TMP:output}});
  page=await browser.newPage({viewport:{width:1440,height:900}});page.setDefaultTimeout(15000);
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('console',message=>{if(message.type()==='error'&&/Shader Error|VALIDATE_STATUS|compile|syntax/i.test(message.text()))errors.push(message.text());});
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.origin!==new URL(info.url).origin)return route.abort();
    if(!url.pathname.endsWith('/livery-scene.js'))return route.continue();
    const response=await route.fetch();
    return route.fulfill({response,body:await response.text()+`
      window.__inspectionTest={state:()=>inspectionState({resources:true}),frames:()=>renderedFrames,
        settle(){controls.autoRotate=false;controls.enableDamping=false;requestRender();},
        invalid:()=>setInspectionHighlight('not-a-section'),
        filter:name=>setSectionFilter(name),
        snapshot(){renderer.render(scene,camera);const gl=renderer.getContext(),w=gl.drawingBufferWidth,h=gl.drawingBufferHeight,p=new Uint8Array(w*h*4);
          gl.readPixels(0,0,w,h,gl.RGBA,gl.UNSIGNED_BYTE,p);let hash=2166136261;const colours=new Set();
          for(let i=0;i<p.length;i+=16){colours.add([p[i]>>4,p[i+1]>>4,p[i+2]>>4].join(','));for(let k=0;k<3;k++)hash=Math.imul(hash^p[i+k],16777619);}
          return {hash:hash>>>0,colours:colours.size,camera:[...camera.position.toArray(),...controls.target.toArray()],
            textures:renderer.info.memory.textures,geometries:renderer.info.memory.geometries,
            enabled:[...paintMaterials,...glassMaterials].map(m=>[...m.uniforms.enabledSlots.value])};}};`});
  });
  await page.goto(info.url,{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>window.__liveryLab?.ready,null,{timeout:120000});
  const project=await page.evaluate(()=>window.__liveryLab.getProject());
  project.vinyls=['a','b','unused'].map((id,index)=>({id,name:id==='a'?'Source <A>':'Source '+id,
    shapes:[{type:1048677,data:[0,0,1,1,0,0,0],color:index?[20,210,180,255]:[255,70,100,255]}]}));
  project.placements=[['p1','a','Top'],['p2','a','Right'],['p3','b','Top'],['p4','b','Right']].map(([id,vinylId,section],index)=>
    ({id,vinylId,section,x:index*40,y:0,scaleX:1,scaleY:1,rotation:0,opacity:1,visible:true}));
  project.authoring={version:1,groups:[{id:'g1',name:'Mixed group',placements:['p1','p3']}],locked:[],links:[]};
  await page.setInputFiles('#projectFile',{name:'source-actions.kfps-layout.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(project))});
  await page.waitForFunction(()=>window.__liveryLab.getProject().placements.length===4);
  const original=await page.evaluate(()=>window.__liveryLab.getProject());
  await page.click('[data-placement=p2]',{modifiers:['Alt']});
  await page.click('[data-inspector-tab=placement]');await page.click('#lockSelection');
  await page.click('[data-source=a]',{button:'right'});
  assert(await page.locator('#deleteSource').isDisabled());await page.keyboard.press('Escape');
  assert.equal(await page.locator('#sourceMenu').isVisible(),false);
  await page.click('#undo');
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),original);
  checks.push('Locked use blocks source deletion; cancellation does not mutate project');

  await page.click('[data-source=b]');await page.click('[data-source=a]',{button:'right'});
  await page.screenshot({path:path.join(output,'source-context-menu.png')});
  await page.mouse.click(800,100);assert.equal(await page.locator('#sourceMenu').isVisible(),false);
  await page.locator('[data-source=a]').dispatchEvent('contextmenu',{clientX:1439,clientY:899});
  const menuBox=await page.locator('#sourceMenu').boundingBox();assert(menuBox.x+menuBox.width<=1440&&menuBox.y+menuBox.height<=900);
  await page.click('#deleteSource');
  assert(await page.locator('#undo').isDisabled());assert(await page.locator('[data-inspection-highlight]').isDisabled());
  assert((await page.locator('#deleteSourceSummary').innerText()).includes('Source <A>'));
  assert.equal(await page.locator('#deleteSourceSummary a').count(),0);
  await page.click('#confirmDeleteSource button[value=cancel]');
  await page.waitForFunction(()=>!document.querySelector('[data-source=a]').disabled);
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),original);
  await page.locator('[data-source=a]').focus();await page.keyboard.press('Shift+F10');
  await page.click('#deleteSource');await page.click('#confirmDeleteSource button[value=delete]');
  await page.waitForFunction(()=>window.__liveryLab.getProject().placements.length===2);
  let deleted=await page.evaluate(()=>window.__liveryLab.getProject());
  assert.deepEqual(deleted.vinyls.map(v=>v.id),['b','unused']);assert.equal(deleted.authoring,undefined);
  assert.deepEqual(deleted.placements.map(p=>p.id),['p3','p4']);
  await page.click('#undo');assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),original);
  await page.click('#redo');assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),deleted);
  checks.push('Right-click and keyboard menu; safe name display; confirmation; all uses; Undo/Redo');
  await page.click('#saveProject');await page.fill('#layoutProjectName','Source deletion QA');
  await page.click('#saveLayoutProject [data-storage=save]');await page.waitForFunction(()=>!document.querySelector('#saveLayoutProject').open);
  await page.click('#undo');await page.click('#redo');
  await page.click('#openProject');await page.selectOption('#openLayoutProject select',{label:'Source deletion QA'});
  await page.click('#openLayoutProject [data-storage=open]');await page.waitForFunction(()=>!document.querySelector('#openLayoutProject').open);
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),deleted);
  checks.push('Deleted layout saved and reopened intact');
  await page.click('[data-source=unused]',{button:'right'});await page.click('#deleteSource');
  await page.waitForFunction(()=>window.__liveryLab.getProject().vinyls.length===1);
  assert.equal(await page.locator('#confirmDeleteSource').isVisible(),false);
  await page.click('[data-source=b]',{button:'right'});await page.click('#deleteSource');
  await page.click('#confirmDeleteSource button[value=delete]');
  await page.waitForFunction(()=>window.__liveryLab.getProject().vinyls.length===0);
  assert(await page.locator('#placeSource').isDisabled());assert(await page.locator('#exportSource').isDisabled());
  await page.click('#undo');await page.waitForFunction(()=>window.__liveryLab.getProject().placements.length===2);
  checks.push('Unused and final source deletion; empty controls and Undo recovery');

  await page.click('[data-inspector-tab=view]');
  const select='[data-inspection-controls] select',highlight='[data-inspection-highlight]';
  await page.selectOption(select,'Right');await page.click('[data-inspection-focus]');
  await page.evaluate(()=>window.__inspectionTest.settle());await sleep(250);
  const before=await page.evaluate(()=>({document:window.__liveryLab.getProject(),state:window.__inspectionTest.state(),image:window.__inspectionTest.snapshot()}));
  assert(before.image.colours>20,'Blank car canvas');assert.equal(before.state.highlightSection,null);
  await page.check(highlight);
  const active=await page.evaluate(()=>({document:window.__liveryLab.getProject(),state:window.__inspectionTest.state(),image:window.__inspectionTest.snapshot()}));
  assert.equal(active.state.highlightSection,'Right');assert.notEqual(active.image.hash,before.image.hash);
  assert.equal(await page.locator('[data-inspection-controls] [role=status]').innerText(),'Highlighted: Right');
  assert.deepEqual(active.image.camera,before.image.camera);assert.deepEqual(active.document,before.document);
  assert.deepEqual(active.image.enabled,before.image.enabled);
  assert.equal(active.state.materialIdentity,before.state.materialIdentity);assert.equal(active.state.geometryIdentity,before.state.geometryIdentity);
  assert.equal(active.image.textures,before.image.textures);assert.equal(active.image.geometries,before.image.geometries);
  await page.screenshot({path:path.join(output,'right-highlight.png')});
  await page.selectOption(select,'Top');assert.equal(await page.evaluate(()=>window.__inspectionTest.state().highlightSection),'Top');
  assert.deepEqual(await page.evaluate(()=>window.__inspectionTest.snapshot().camera),before.image.camera);
  assert.equal(await page.evaluate(()=>window.__inspectionTest.invalid()),false);
  await page.uncheck(highlight);
  const off=await page.evaluate(()=>window.__inspectionTest.snapshot());assert.equal(off.hash,before.image.hash);
  checks.push('Highlight changes real canvas pixels, follows dropdown, restores exact image; no document/camera/resource change');
  // The chosen mask remains inspectable when another decal section is filtered.
  await page.selectOption(select,'Right');await page.evaluate(()=>window.__inspectionTest.filter('top'));
  const filtered=await page.evaluate(()=>window.__inspectionTest.snapshot());await page.check(highlight);
  const filteredHighlight=await page.evaluate(()=>window.__inspectionTest.snapshot());
  assert.notEqual(filtered.hash,filteredHighlight.hash);assert.deepEqual(filtered.enabled,filteredHighlight.enabled);
  await page.uncheck(highlight);await page.evaluate(()=>window.__inspectionTest.filter('all'));
  for(const mode of ['paintability','uv-seams','off']){
    await page.click(`[data-inspection-mode="${mode}"]`);await page.check(highlight);await page.uncheck(highlight);
  }
  assert.equal(await page.evaluate(()=>window.__inspectionTest.state().ownedGeometries),0);
  assert.deepEqual(await page.evaluate(()=>window.__liveryLab.getProject()),before.document);
  const frames=await page.evaluate(()=>window.__inspectionTest.frames());await sleep(1000);
  assert((await page.evaluate(()=>window.__inspectionTest.frames()))-frames<8,'Continuous idle rendering');
  checks.push('Section filter independent; inspection modes coexist; UV resources released; renderer idles');
  await page.setViewportSize({width:960,height:720});await page.screenshot({path:path.join(output,'narrow-inspection.png')});
  const bounds=await page.locator('.inspection-highlight').boundingBox();assert(bounds&&bounds.width>100&&bounds.x>=0&&bounds.x+bounds.width<=960);
  assert.deepEqual(errors,[]);evidence.checks=checks;evidence.pixels={before:before.image,active:active.image,off};
  console.log(JSON.stringify({passed:checks,errors},null,2));
}catch(error){
  await page?.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});
  if(page)fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify(await page.evaluate(()=>({text:document.body.innerText,project:window.__liveryLab?.getProject()})).catch(()=>null),null,2));
  throw error;
}finally{
  fs.writeFileSync(path.join(output,'evidence.json'),JSON.stringify({...evidence,checks,errors},null,2));
  await browser?.close();if(child.exitCode===null){child.kill();await new Promise(resolve=>child.once('exit',resolve));}fs.closeSync(log);
}
