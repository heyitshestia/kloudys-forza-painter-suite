import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const web = path.join(root,'tools/livery-studio/src/web');
const temporary = path.join(root,'runtime/studio-package-workspace-20261102');
const require = createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium} = require('playwright');
const first = 'a'.repeat(43), second = 'b'.repeat(43), id = 'c'.repeat(32), job = 'd'.repeat(32);
const vehicle = {car_id:3307,model_code:'PACKAGE_CAR'};
const origin = 'http://127.0.0.1:32198';
const browser = await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args:['--disable-gpu'],env:{...process.env,TEMP:temporary,TMP:temporary}});
try {
  for(const mode of ['ordinary','cold-exact','native-owned','native-shared','native-mixed','chrome','ambiguous']) {
    const context = await browser.newContext(), page = await context.newPage(), calls = [], errors = [];
    page.on('pageerror',error=>errors.push(String(error)));
    if(mode.startsWith('native') || mode==='ambiguous')await context.addInitScript(()=>{window.__kfpsStudioNativeDownloads=true;});
    await context.route('**/*',async route=>{
      const url = new URL(route.request().url());
      if(url.origin !== origin)return route.abort();
      const [,token,...parts] = url.pathname.split('/'), relative = parts.join('/');
      calls.push({token,relative});
      if(relative==='api/language')return route.fulfill({json:{language:'en'}});
      if(relative==='api/editor-config')return route.fulfill({json:{host_layout_handoff:true,car_switch:true,chrome_exposed:mode==='native-mixed',
        vehicle:mode==='cold-exact'||token===second?vehicle:{car_id:99,model_code:'DEFAULT'}}});
      if(relative.startsWith('api/host-layout/'))return route.fulfill({json:{name:'Fixture',
        ...(mode==='native-shared'?{}:{startup_session:`${origin}/${first}/`}),
        layout:{format:'kfps-livery-layout-v1',vehicle,vinyls:[],placements:[]}}});
      if(relative==='api/cars')return route.fulfill({json:{current:null,cars:[{id,...vehicle},
        ...(mode==='ambiguous'?[{id:'e'.repeat(32),...vehicle}]:[])]}});
      if(relative==='api/car-switch')return route.fulfill({json:{id:job,status:'ready'}});
      if(relative===`api/car-switch/${job}/commit`)return route.fulfill({json:{id:job,status:'committed',url:`${origin}/${second}/`}});
      if(relative==='theme-adapter.mjs')return route.fulfill({contentType:'application/javascript',
        body:'export async function initializeTheme(){document.documentElement.removeAttribute("data-theme-loading");}'});
      if(relative==='livery-editor.mjs')return route.fulfill({contentType:'application/javascript',
        body:'import "./livery-scene.js"; import {takePackageStartupHandoff} from "./studio-bootstrap.mjs"; window.__fixtureHandoff=takePackageStartupHandoff(location.hash.slice(8)); window.__fixtureEditorReady=true;'});
      if(relative==='livery-scene.js')return route.fulfill({contentType:'application/javascript',body:'window.__fixtureSceneReady=true;'});
      if(/^(release-announcement|activity-client)\.js$/.test(relative))return route.fulfill({contentType:'application/javascript',body:''});
      const file = path.resolve(web,relative||'index.html');
      if(!file.startsWith(web+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())return route.fulfill({status:404,body:''});
      return route.fulfill({contentType:/\.(js|mjs)$/.test(file)?'application/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(file)});
    });
    await page.goto(`${origin}/${first}/${mode==='ordinary'?'':'#layout='+id}`);
    if(['native-shared','native-mixed','chrome','ambiguous'].includes(mode)) {
      await page.waitForFunction(()=>window.__liveryLabBootError);
      assert.equal(calls.some(call=>call.relative==='livery-editor.mjs'||call.relative==='livery-scene.js'),false);
      assert.equal(calls.some(call=>call.relative==='api/car-switch'),false);
    } else {
      await page.waitForFunction(()=>window.__fixtureEditorReady);
      assert.equal(await page.evaluate(()=>window.__fixtureSceneReady),true);
      if(mode!=='ordinary') {
        assert.deepEqual(await page.evaluate(()=>window.__fixtureHandoff.layout.vehicle),vehicle);
        const token=mode==='native-owned'?second:first;
        assert.equal(calls.filter(call=>call.token===token&&call.relative.startsWith('api/host-layout/')).length,1);
      }
      if(mode==='native-owned') {
        assert.equal(calls.filter(call=>call.relative==='api/car-switch').length,1);
        assert.equal(calls.some(call=>call.token===first && call.relative==='livery-scene.js'),false);
        assert.equal(new URL(page.url()).pathname,`/${second}/`);
        assert.equal(new URL(page.url()).hash,'#layout='+id);
      } else assert.equal(calls.some(call=>call.relative==='api/car-switch'),false);
    }
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({mode,passed:true,sceneLoads:calls.filter(call=>call.relative==='livery-scene.js').length}));
    await context.close();
  }
} finally {
  await browser.close();
}
