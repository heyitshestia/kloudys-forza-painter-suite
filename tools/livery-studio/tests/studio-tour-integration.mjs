import assert from 'node:assert/strict';
import fs from 'node:fs';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {studioTourSteps} from '../src/web/studio-tour.mjs';

// Run the actual HTTP server, editor and tour. The scene and data APIs are
// synthetic: no car models, user files, native windows or GPU rendering are used.
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const web=path.join(root,'tools/livery-studio/src/web');
const output=path.join(root,'runtime/studio-completion-20261111/tour/integration');
fs.mkdirSync(output,{recursive:true});
const require=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium}=require('playwright');
const vehicle={car_id:1,model_code:'SYNTHETIC_TOUR'};
const config={vehicle,paint_size:[64,32],sections:[{section:'Left',atlasToLocal:[1,0,0,0,1,0],source_region:[0,0,1,1],paint_region:[0,0,1,1]}],
  project_storage:{enabled:true},vinyl_library:{enabled:true},recovery:{enabled:true,debounce_ms:60000},section_vinyl_export:true,host_project_handoff:true,
  experimental_export:{enabled:true},livery_package_export:true};
const project={format:'kfps-livery-layout-v1',vehicle,
  vinyls:[{id:'source',name:'Synthetic source',shapes:[{type:1048677,data:[0,0,1,1,0,0,0],color:[250,20,130,255],mask:false}]}],
  placements:['one','two','three'].map((id,index)=>({id,vinylId:'source',section:'Left',x:index*100,y:0,scaleX:1,scaleY:1,rotation:0,opacity:1,visible:true})),
  authoring:{version:1,groups:[{id:'pair',name:'Pair',placements:['one','two']}],locked:['three'],links:[]}};
const scene=`
  let parts={},paintUpdates=0,mode='off',highlightSection=null;
  export const sceneReady=Promise.resolve(),isSceneReady=()=>true;
  export const sceneState=()=>({device:{maxTextureSize:16384},bytes:{estimatedGpu:0,budget:1024**3}});
  export const sceneDiagnosticMetrics=()=>({});
  export const updatePaintCanvas=()=>{paintUpdates++;};
  export const currentVehicleParts=()=>structuredClone(parts);
  export const validatePartConfiguration=value=>value||{};
  export const setVehicleParts=value=>(parts=structuredClone(value||{}));
  export const garageVehicleParts=()=>({});
  export const configureSurfaceEditing=()=>{},surfaceAtClient=()=>null,surfaceCameraEnabled=()=>{},setSurfaceSelection=()=>{};
  export const setInspectionMode=value=>(mode=value,true),setInspectionHighlight=value=>(highlightSection=value,true);
  export const inspectionState=()=>({ready:true,mode,sections:['Left'],highlightSection,lineSegments:0,seamUnavailable:0});
  export const focusInspectionSection=()=>true;
  window.__tourScene={paintUpdates:()=>paintUpdates};
  document.getElementById('status').classList.add('hidden');
`;
const probe=`
  window.__tourIntegration={
    open:()=>studioTour.open(),close:()=>studioTour.close(),
    state:()=>({project:structuredClone(project),selection:[...selectedIds],section:$('section').value,source:pickedSource,
      saved,dirty:changed(),undo:history.canUndo,redo:history.canRedo,quality:activeQuality,mode:surfaceMode}),
    guard:(name,value)=>{switch(name){case 'busy':busy=value;break;case 'save':saveWorking=value;break;
      case 'loading':sessionLoading=value;break;case 'handoff':handoffWorking=value;break;case 'car':carWorking=value;break;
      case 'drag':drag=value?{}:null;break;case 'transform':transform=value?{}:null;break;
      case 'picker':externalPicker=value?{}:null;break;case 'slider':sliderPointer=value?{}:null;break;}}
  };
`;
const fixture=path.join(output,'http-fixture');fs.mkdirSync(fixture,{recursive:true});
const backendScript=`
import json, os, sys, webbrowser
from pathlib import Path
from types import SimpleNamespace
root, fixture = Path(sys.argv[1]), Path(sys.argv[2])
def capture_open(entry, *args, **kwargs):
    if (fixture / 'manual-fail-once').exists():
        (fixture / 'manual-fail-once').unlink()
        raise OSError('Test-only missing browser association')
    (fixture / 'manual-opened.json').write_text(json.dumps(str(entry)))
    return True
if os.name == 'nt':
    os.startfile = capture_open
else:
    webbrowser.open = capture_open
sys.path[:0] = [str(root / 'tools/livery-studio/src')]
from kfps_livery_lab import server, diagnostics, source_editor, confirmation_preferences, language_preferences, preview_preferences, theme_context
# Relocate fixture roots only; keep production containment checks and handlers.
for module in (server, confirmation_preferences, language_preferences, preview_preferences, theme_context):
    module.LAB_ROOT = fixture
source_editor.LAB = fixture
diagnostics.DEFAULT_ROOT = fixture / 'diagnostics'
workspace = fixture / 'runs/session'
workspace.mkdir(parents=True, exist_ok=True)
for name in ('mesh.glb', 'paint.png', 'm0.png', 'm1.png', 'm2.png'):
    (workspace / name).write_bytes(b'synthetic-unused-asset')
prepared = dict(files=dict(mesh='mesh.glb', paint='paint.png', masks=['m0.png','m1.png','m2.png']),
                manifest=dict(inspection_runtime=dict(local_mesh=True)), editor_config=json.loads(sys.argv[3]))
host = server.LiveryLabServer(prepared, workspace, root,
    web_root=root / 'tools/livery-studio/src/web', renderer=lambda *args, **kwargs: {},
    session_data_root=workspace / 'session-data', release_announcement=SimpleNamespace(close=lambda: None))
try:
    print(json.dumps(dict(url=host.start())), flush=True)
    sys.stdin.readline()
finally:
    host.close()
`;
const log=fs.openSync(path.join(output,'http-server.log'),'w');
const child=spawn(path.join(root,'python/python.exe'),['-I','-B','-c',backendScript,root,fixture,JSON.stringify(config)],
  {cwd:root,windowsHide:true,stdio:['pipe','pipe',log],env:{...process.env,KFPS_ACTIVITY_DISABLED:'1',TEMP:fixture,TMP:fixture,LOCALAPPDATA:fixture,APPDATA:fixture}});
let stdout='',exitCode=null;const exited=new Promise(resolve=>child.once('exit',code=>{exitCode=code;resolve(code);}));
child.stdout.on('data',chunk=>{stdout+=chunk;});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const results=[];let browser,page,failure=null;
try{
  for(let i=0;i<150&&!stdout.includes('\n')&&child.exitCode===null;i++)await sleep(100);
  assert(stdout.includes('\n'),'Real HTTP server did not start; see http-server.log');
  const base=JSON.parse(stdout.trim().split('\n')[0]).url,origin=new URL(base).origin,basePath=new URL(base).pathname;
  const staticResults=[];
  for(const name of ['studio-tour.mjs','studio-tour.css']){
    const response=await fetch(base+name),body=Buffer.from(await response.arrayBuffer());
    assert.equal(response.status,200,`Actual server does not serve ${name}`);
    const contentType=response.headers.get('content-type');
    assert.match(contentType,name.endsWith('.mjs')?/^(text|application)\/javascript/:/^text\/css/);
    const digest=data=>createHash('sha256').update(data).digest('hex');
    assert.equal(digest(body),digest(fs.readFileSync(path.join(web,name))),'HTTP bytes differ from working source');
    const unscoped=await fetch(origin+'/'+name);assert.notEqual(unscoped.status,200,'Static asset escaped session token');
    staticResults.push({name,status:response.status,contentType,sha256:digest(body),unscopedStatus:unscoped.status});
  }
  fs.writeFileSync(path.join(output,'http-static.json'),JSON.stringify(staticResults,null,2));
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args:['--disable-gpu','--disable-software-rasterizer'],env:{...process.env,TEMP:output,TMP:output}});
  for(const language of ['en','ko','ja']){
    page=await browser.newPage({viewport:{width:1280,height:800},reducedMotion:'reduce'});
    const errors=[],unexpected=[],requests=[],exports=[];let stored=null;
    page.on('pageerror',error=>errors.push(String(error)));
    await page.route('**/*',async route=>{
      const request=route.request(),url=new URL(request.url()),name='/'+url.pathname.slice(basePath.length);
      if(url.origin!==origin)return route.abort();
      if(name==='/api/language')return route.fulfill({json:{language}});
      if(name==='/api/editor-config')return route.fulfill({json:config});
      if(name==='/api/preview-quality')return route.fulfill({json:{version:1,quality:'fast'}});
      if(name==='/api/export-package'){
        exports.push(request.postDataJSON());
        return route.fulfill({status:422,json:{error:'The package does not match the current car.'}});
      }
      if(name==='/api/render-vinyl'){
        const png=await page.evaluate(()=>{
          const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=512;
          const context=canvas.getContext('2d');context.fillStyle='#fa1482';context.fillRect(412,156,200,200);
          return canvas.toDataURL();
        });
        return route.fulfill({json:{png,bounds:[824,312,1224,712]}});
      }
      if(name==='/api/projects'&&request.method()==='POST'){
        const body=request.postDataJSON();stored={project:body.project,entry:{id:'synthetic',revision:'1',name:body.name}};
        return route.fulfill({json:stored});
      }
      if(name==='/api/projects')return route.fulfill({json:{entries:stored?[stored.entry]:[],next_offset:null}});
      if(name==='/api/projects/synthetic')return route.fulfill({json:stored});
      if(name==='/api/recovery')return route.fulfill({json:{entries:[]}});
      if(name==='/api/diagnostics')return route.fulfill({json:{ok:true}});
      if(name==='/api/open-manual')return route.continue();
      if(name.startsWith('/api/')){unexpected.push(name);return route.fulfill({status:404,json:{error:'Unexpected test request'}});}
      if(name==='/livery-scene.js')return route.fulfill({contentType:'application/javascript',body:scene});
      if(name==='/livery-editor.mjs'){
        const response=await route.fetch();assert.equal(response.status(),200);
        return route.fulfill({response,body:await response.text()+probe});
      }
      if(name==='/theme-adapter.mjs')return route.fulfill({contentType:'application/javascript',body:'export async function initializeTheme(){document.documentElement.removeAttribute("data-theme-loading");}'});
      if(/\/(release-announcement|activity-client)\.js$/.test(name))return route.fulfill({contentType:'application/javascript',body:''});
      requests.push(name);return route.continue();
    });
    await page.goto(base);
    await page.waitForFunction(()=>window.__liveryLab?.ready||window.__liveryLabBootError,null,{timeout:15000});
    assert.equal(await page.evaluate(()=>window.__liveryLabBootError),undefined);
    const exportContract='Existing template paint and material records are kept; edited artwork is replaced. Studio body-part selections are not written to the export. Game acceptance remains unverified.';
    assert.equal(await page.locator('#confirmExperiment p').last().textContent(),
      await page.evaluate(async key=>(await import('./i18n.mjs')).t(key),exportContract));
    assert.equal(await page.locator('#studioTour').isVisible(),false,'Tour auto-opened');
    assert(await page.locator('#exportPackage').isDisabled(),'An empty design must not be exported');
    await page.locator('#showStudioTour').click();
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(()=>__liveryLab.getProject().placements.length),0);
    // Use the actual file-open handler; no direct project injection.
    await page.locator('#projectFile').setInputFiles({name:'Synthetic.kfps-layout.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(project))});
    await page.waitForFunction(()=>__liveryLab.getProject().placements.length===3,null,{timeout:15000});
    const captured=path.join(fixture,'manual-opened.json');
    fs.rmSync(captured,{force:true});
    fs.rmSync(path.join(fixture,'manual-fail-once'),{force:true});
    for(const [suffix,options,status] of [
      ['', {headers:{Origin:origin}},405],
      ['', {method:'POST'},403],
      ['?file=other', {method:'POST',headers:{Origin:origin}},403],
      ['', {method:'POST',headers:{Origin:origin},body:'{}'},400],
    ]){
      assert.equal((await fetch(base+'api/open-manual'+suffix,options)).status,status);
    }
    assert(!fs.existsSync(captured),'A rejected request opened a browser');
    const manual=page.locator('#showStudioTour + #openStudioManual');
    assert.equal(await manual.innerText(),{en:'Manual',ja:'マニュアル',ko:'사용 설명서'}[language]);
    const initial=await page.evaluate(()=>__tourIntegration.state());
    fs.writeFileSync(path.join(fixture,'manual-fail-once'),'');
    const [failed]=await Promise.all([page.waitForResponse(r=>r.url()===base+'api/open-manual'),manual.click()]);
    assert.equal(failed.status(),503);
    await page.waitForFunction(()=>!document.querySelector('#openStudioManual').disabled &&
      document.querySelector('#notice').textContent.includes('docs/garage-studio-guide/index.html'));
    await manual.focus();
    const [opened]=await Promise.all([page.waitForResponse(r=>r.url()===base+'api/open-manual'),manual.press('Enter')]);
    assert.equal(opened.status(),200);
    await page.waitForFunction(()=>!document.querySelector('#openStudioManual').disabled &&
      !document.querySelector('#notice').classList.contains('error'));
    const entry=JSON.parse(fs.readFileSync(captured,'utf8')),doc=path.join(root,'docs/garage-studio-guide');
    const expected=pathToFileURL(path.join(doc,'studio.html')).href;
    assert.equal(entry.startsWith('file:')?entry:pathToFileURL(entry).href,expected);
    assert.deepEqual(await page.evaluate(()=>__tourIntegration.state()),initial);
    assert.equal(page.url(),base);
    const reader=await browser.newPage();
    for(const [entryName,anchor,title] of [['studio','part-03','Livery Studio'],['garage','part-02','Garage']]){
      await reader.goto(entryName==='studio'?expected:pathToFileURL(path.join(doc,'garage.html')).href);
      await reader.waitForURL(url=>url.hash==='#'+anchor);
      assert.equal(await reader.locator(':target').innerText(),title);
      await reader.waitForFunction(()=>{const r=document.querySelector(':target').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;});
    }
    await reader.close();
    if(language==='en'){
      const broken=await browser.newPage();
      await broken.route('**/*',route=>{
        const url=new URL(route.request().url());
        if(url.origin!==origin || url.pathname.endsWith('/theme-adapter.mjs'))return route.abort();
        if(/\/(activity-client|release-announcement)\.js$/.test(url.pathname))return route.fulfill({contentType:'application/javascript',body:''});
        return route.continue();
      });
      await broken.goto(base);
      await broken.waitForFunction(()=>!!window.__liveryLabBootError);
      const startupError=await broken.locator('#notice').innerText();
      assert(await broken.locator('#showStudioTour').isDisabled());
      const [fallback]=await Promise.all([broken.waitForResponse(r=>r.url()===base+'api/open-manual'),broken.locator('#openStudioManual').click()]);
      assert.equal(fallback.status(),200);
      await broken.waitForFunction(()=>!document.querySelector('#openStudioManual').disabled);
      assert.equal(await broken.locator('#notice').innerText(),startupError);
      await broken.close();
    }
    await page.click('#inspector-tab-project');
    await page.click('#exportPackage');await page.fill('#packageTitle','');await page.click('#packageDialog [value=cancel]');
    assert.equal(exports.length,0,'Cancelling an empty title must not send a request');
    await page.click('#exportPackage');await page.fill('#packageTitle','Test package');
    await page.click('#packageDialog [value=export]');
    await page.waitForFunction(()=>document.querySelector('#experimentStatus').classList.contains('error')&&!document.querySelector('#exportPackage').disabled);
    assert.equal(exports.length,1);assert.equal(exports[0].title,'Test package');
    assert.deepEqual(exports[0].project,await page.evaluate(()=>__liveryLab.getProject()));
    await page.click('#inspector-tab-placement');
    await page.locator('#placementList [data-placement=two]').click({modifiers:['Alt']});
    await page.locator('#positionX').fill('123.5');
    const pristine=await page.evaluate(()=>__tourIntegration.state());
    await page.locator('#showStudioTour').click();
    assert.equal(await page.locator('#studioTour').isVisible(),false,'Valid numeric draft committed by tour');
    assert.equal(await page.locator('#positionX').inputValue(),'123.5');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'positionX');
    assert.deepEqual(await page.evaluate(()=>__tourIntegration.state()),pristine);
    await page.keyboard.press('Escape');
    await page.locator('#positionX').fill('');await page.locator('#showStudioTour').click();
    assert.equal(await page.locator('#studioTour').isVisible(),false,'Invalid draft hidden by tour');
    assert.equal(await page.locator('#positionX').inputValue(),'');
    await page.keyboard.press('Escape');
    // Retain a real edit and a redo entry to check undo history and dirty state.
    await page.locator('#positionX').fill('140');await page.locator('#selectionName').click();
    await page.locator('#undo').click();
    const before=await page.evaluate(()=>__tourIntegration.state());assert(before.redo);
    for(const name of ['busy','save','loading','handoff','car','drag','transform','picker','slider']){
      assert.equal(await page.evaluate(name=>{
        __tourIntegration.guard(name,true);const opened=__tourIntegration.open();__tourIntegration.guard(name,false);return opened;
      },name),false,`Admission during ${name}`);
    }
    await page.locator('#showShortcuts').click();
    assert.equal(await page.evaluate(()=>__tourIntegration.open()),false);
    assert.equal(await page.locator('#shortcuts').evaluate(node=>node.open),true,'Existing dialog changed');
    await page.keyboard.press('Escape');
    await page.locator('#showStudioTour').click();
    for(const step of studioTourSteps){
      assert.equal(await page.locator('#studioTour').getAttribute('data-step'),step.id);
      assert.equal(await page.locator('.studio-tour-spotlight').isVisible(),true,`Real control missing: ${step.id}`);
      for(const key of ['Control+z','Control+y','Control+d','Control+s','Delete','ArrowRight','v','r'])await page.keyboard.press(key);
      assert.deepEqual(await page.evaluate(()=>__tourIntegration.state()),before,`Changed state: ${step.id}`);
      if(step.id==='export')await page.screenshot({path:path.join(output,`${language}-editor-export.png`)});
      await page.locator('[data-tour-next]').click();
    }
    assert.deepEqual(await page.evaluate(()=>__tourIntegration.state()),before);
    // Command-search integration uses the real registered command and dispatch.
    await page.locator('#workspaceSearch').click();
    await page.locator('#workspaceCommandSearch input').fill(await page.locator('#showStudioTour').getAttribute('title'));
    await page.keyboard.press('Enter');await page.waitForFunction(()=>document.getElementById('studioTour').open);
    const paintUpdates=await page.evaluate(()=>__tourScene.paintUpdates());
    await page.waitForTimeout(1000);
    assert.equal(await page.evaluate(()=>__tourScene.paintUpdates()),paintUpdates,'Tour schedules idle paint work');
    await page.evaluate(()=>{location.hash='#project='+'a'.repeat(32);});
    await page.waitForFunction(()=>document.getElementById('hostTransferMessage').textContent.length>0);
    assert.equal(await page.locator('#hostTransferMessage').textContent(),await page.evaluate(async()=>
      (await import('./i18n.mjs')).t('Finish the current edit, then retry the incoming vinyl.')));
    assert.deepEqual(unexpected,[],'Incoming handoff fetched while tour open');
    await page.evaluate(()=>history.replaceState(null,'',location.pathname));
    await page.keyboard.press('Escape');
    assert.deepEqual(await page.evaluate(()=>__tourIntegration.state()),before);
    // Named save and reopen use the real project UI, with memory-only storage.
    await page.locator('#saveProject').click();await page.locator('#layoutProjectName').fill('Tour roundtrip');
    await page.locator('#saveLayoutProject [data-storage=save]').click();
    await page.waitForFunction(()=>!document.getElementById('saveLayoutProject').open);
    assert.deepEqual(stored.project,before.project);
    await page.locator('#openProject').click();await page.locator('#openLayoutProject select').selectOption('synthetic');
    await page.locator('#openLayoutProject [data-storage=open]').click();
    await page.waitForFunction(()=>!document.getElementById('openLayoutProject').open);
    assert.deepEqual(await page.evaluate(()=>__liveryLab.getProject()),before.project);
    await page.setViewportSize({width:360,height:480});await page.locator('#showStudioTour').click();
    for(let i=0;i<studioTourSteps.findIndex(s=>s.id==='inspection');i++)await page.locator('[data-tour-next]').click();
    await page.screenshot({path:path.join(output,`${language}-compact-inspection.png`)});
    await page.evaluate(()=>window.dispatchEvent(new CustomEvent('kfps-viewer-error',{detail:{message:'Synthetic preview failure'}})));
    assert.equal(await page.locator('#studioTour').isVisible(),false,'Preview failure left tour over recovery');
    assert.deepEqual(await page.evaluate(()=>__liveryLab.getProject()),before.project);
    assert.equal(await page.locator('#previewRecovery').isVisible(),true);
    await page.evaluate(()=>window.dispatchEvent(new PageTransitionEvent('pagehide')));
    assert.equal(await page.locator('#studioTour').count(),0);
    assert.equal(await page.locator('#showStudioTour').isDisabled(),true);
    assert.deepEqual(errors,[]);assert.deepEqual(unexpected,[]);
    assert(!requests.some(name=>name.startsWith('/vendor/three/')),'Real GPU scene was loaded');
    results.push({language,steps:studioTourSteps.length,manualChaptersAndRetry:true,documentAndSelectionPreserved:true,numericDraftsProtected:true,
      busyGuards:9,modalsPreserved:true,commandSearch:true,historyPreserved:true,saveReopen:true,
      previewFailureRecovery:true,pagehideCleanup:true,idlePaintDelta:0,realScene:false,errors});
    await page.close();page=null;
  }
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}catch(error){
  failure=error;
  if(page){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});
    fs.writeFileSync(path.join(output,'failure.json'),JSON.stringify({error:String(error),body:await page.locator('body').innerText()},null,2));}
  throw error;
}finally{
  await browser?.close();child.stdin.end();
  let forced=false,timer;
  try{await Promise.race([exited,new Promise(resolve=>{timer=setTimeout(resolve,8000);})]);}
  finally{clearTimeout(timer);}
  if(child.exitCode===null){forced=true;child.kill();await exited;}
  fs.closeSync(log);
  fs.writeFileSync(path.join(output,'http-cleanup.json'),JSON.stringify({pid:child.pid,exitCode,forced,browserClosed:true},null,2));
  if(!failure){assert.equal(forced,false,'Owned test server needed forced cleanup');assert.equal(exitCode,0,'Owned test server exited unsuccessfully');}
}
