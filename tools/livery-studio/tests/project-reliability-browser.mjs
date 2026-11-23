import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const output=path.join(root,'runtime/studio-completion-20261111/project-reliability/browser');
fs.mkdirSync(output,{recursive:true});
const require=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium}=require('playwright');
const child=spawn(path.join(root,'python/python.exe'),['-I','-B','KFPS.UI/tests/test_studio_project_reliability.py','--serve'],
  {cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,QT_QPA_PLATFORM:'offscreen'}});
let stderr='',browser,finished=false;
child.stderr.on('data',data=>{stderr+=data;});
const exited=new Promise(resolve=>child.once('exit',(code,signal)=>resolve({code,signal})));
const lines=createInterface({input:child.stdout});
const ready=new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(Error('Fixture startup timed out')),15000);
  lines.once('line',line=>{clearTimeout(timer);try{resolve(JSON.parse(line));}catch(error){reject(error);}});
  child.once('error',error=>{clearTimeout(timer);reject(error);});
  child.once('exit',()=>{clearTimeout(timer);reject(Error('Fixture exited before readiness'));});
});
const checks=[];
try{
  const {url}=await ready;
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args:['--disable-gpu','--disable-software-rasterizer'],env:{...process.env,TEMP:output,TMP:output}});
  const page=await browser.newPage({viewport:{width:1100,height:760}}),errors=[];
  page.setDefaultTimeout(10000);
  page.on('pageerror',error=>errors.push(String(error)));
  const initialize=async()=>{
    await page.goto(url);
    await page.evaluate(async()=>{
      const {initProjectStorage}=await import('./project-storage-ui.mjs');
      const {initRecovery}=await import('./recovery-ui.mjs');
      let value={format:'kfps-livery-layout-v1',vehicle:{car_id:3307,model_code:'TEST_CAR'},vinyls:[
        {id:'s',name:'Source',shapes:[{type:1048677,data:[0,0,1,1,0,0,0],color:[0,255,0,255]}]}],
        placements:[{id:'p',vinylId:'s',section:'Front',x:0,y:0,scaleX:1,scaleY:1,rotation:0,opacity:1,visible:true}]};
      let revision=0,apiCalls=[],pause=false,release=null,loading=false;
      const api=async(route,body)=>{
        apiCalls.push([route,body!==undefined]);
        const response=await fetch('./api/'+route,{method:body===undefined?'GET':'POST',
          headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
        const result=await response.json();if(!response.ok)throw Object.assign(Error(result.error),result);return result;
      };
      const loadProject=async(next,{isCurrent})=>{
        loading=true;
        try{if(pause)await new Promise(resolve=>{release=resolve;});if(!isCurrent())return false;
          value=structuredClone(next);revision++;return true;
        }finally{loading=false;}
      };
      const storage=initProjectStorage({api,getProject:()=>value,getDocumentRevision:()=>revision,
        loadProject,defaultName:()=> 'Fixture',message:()=>{},importVinyl:async()=>{},readVinyl:async()=>{},
        externalProject:()=>{},externalVinyl:()=>{}});
      const recovery=initRecovery({host:document.querySelector('#recoveryHost'),api,getProject:()=>value,
        loadProject,config:{recovery:{debounce_ms:10000}}});
      window.qa={storage,recovery,api,apiCalls,project:()=>structuredClone(value),
        move:x=>{value.placements[0].x=x;revision++;},pause:()=>{pause=true;},release:()=>release?.(),loading:()=>loading,
        save:()=>{window.qa.saved='pending';void storage.save().then(result=>{window.qa.saved=result;});}};
    });
    await page.waitForFunction(()=>!document.querySelector('[data-recovery=open]').disabled);
  };
  await initialize();
  await page.evaluate(()=>qa.save());
  await page.click('[data-storage=cancel-save]');
  await page.waitForFunction(()=>qa.saved===null);
  assert.equal(await page.evaluate(()=>qa.apiCalls.filter(([route,post])=>route==='projects'&&post).length),0);
  checks.push('cancel before save: no write');

  await page.evaluate(()=>qa.save());await page.click('[data-storage=save]');
  await page.waitForFunction(()=>qa.saved&&qa.saved!=='pending');
  const saved=await page.evaluate(()=>qa.saved.entry);
  assert.equal((await page.evaluate(id=>qa.api('projects/'+id),saved.id)).project.placements[0].x,0);
  checks.push('managed save reopens through actual HTTP');

  await page.evaluate(()=>{qa.move(55);qa.storage.open();});
  await page.selectOption('[data-storage=projects]',saved.id);
  await page.waitForFunction(()=>!document.querySelector('[data-storage=open]').disabled);
  await page.click('[data-storage=cancel-open]');
  assert.equal(await page.evaluate(()=>qa.project().placements[0].x),55);
  checks.push('cancel open: current edits unchanged');

  await page.evaluate(()=>{
    qa.save();
    document.querySelector('[data-storage=cancel-save]').click();
    qa.storage.open();
  });
  await page.waitForFunction(()=>!document.querySelector('#openLayoutProject').innerText.includes('Loading projects...'));
  await page.click('[data-storage=cancel-open]');
  checks.push('queued save close cannot cancel a newly opened project dialog');

  await page.evaluate(()=>{qa.pause();qa.storage.open();});
  await page.selectOption('[data-storage=projects]',saved.id);
  await page.waitForFunction(()=>!document.querySelector('[data-storage=open]').disabled);
  await page.click('[data-storage=open]');await page.waitForFunction(()=>qa.loading());
  await page.evaluate(()=>{qa.storage.dispose();qa.release();});
  await page.waitForFunction(()=>!qa.loading());
  assert.equal(await page.evaluate(()=>qa.project().placements[0].x),55);
  checks.push('dispose during prepared open: late load cancelled');

  await initialize();await page.evaluate(()=>{qa.move(66);qa.save();});
  await page.click('[data-storage=save]');await page.waitForFunction(()=>!document.querySelector('[data-storage=replace]').hidden);
  await page.click('[data-storage=cancel-save]');await page.waitForFunction(()=>qa.saved===null);
  assert.equal((await page.evaluate(id=>qa.api('projects/'+id),saved.id)).project.placements[0].x,0);
  await page.evaluate(()=>qa.save());await page.click('[data-storage=save]');
  await page.waitForFunction(()=>!document.querySelector('[data-storage=replace]').hidden);
  await page.click('[data-storage=replace]');await page.waitForFunction(()=>qa.saved&&qa.saved!=='pending');
  assert.equal((await page.evaluate(id=>qa.api('projects/'+id),saved.id)).project.placements[0].x,66);
  checks.push('reload and replace conflict: cancel preserves, explicit replace updates');

  await page.click('[data-recovery=open]');await page.fill('[data-recovery=name]','Before edit');
  await page.click('[data-recovery=checkpoint]');
  await page.waitForFunction(()=>document.querySelector('[data-recovery=entries]').options.length===1&&
    !document.querySelector('[data-recovery=restore]').disabled&&document.querySelector('[data-recovery=entries]').value);
  await page.click('[data-recovery=close]');await page.evaluate(()=>qa.move(99));
  await page.click('[data-recovery=open]');await page.waitForFunction(()=>!document.querySelector('[data-recovery=restore]').disabled);
  await page.click('[data-recovery=restore]');await page.click('[data-recovery=cancel-restore]');
  assert.equal(await page.evaluate(()=>qa.project().placements[0].x),99);
  checks.push('cancel recovery confirmation: no layout replacement');
  await page.click('[data-recovery=restore]');
  await page.screenshot({path:path.join(output,'restore-confirmation.png')});
  await page.click('[data-recovery=confirm-restore]');
  await page.waitForFunction(()=>qa.project().placements[0].x===66);
  const entries=(await page.evaluate(()=>qa.api('recovery'))).entries;
  assert.equal(entries.length,2);assert(entries.some(entry=>entry.kind==='before-restore'));
  checks.push('recovery restore retains edited layout before replacement');
  await initialize();await page.click('[data-recovery=open]');
  await page.waitForFunction(()=>document.querySelector('[data-recovery=entries]').options.length===2);
  checks.push('page restart preserves project catalogue and recovery list');
  assert.deepEqual(errors,[]);
  await page.evaluate(()=>{qa.storage.dispose();qa.recovery.dispose();});
  await page.close();
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({checks,passed:checks.length,headless:true,gpu:false,
    limitation:'Actual storage routes and dialog controllers; resource staging uses a no-render loader.'},null,2));
  finished=true;console.log(JSON.stringify({passed:checks.length,output}));
}finally{
  if(!finished&&browser){
    const page=browser.contexts()[0]?.pages()[0];
    if(page&&!page.isClosed()){
      fs.writeFileSync(path.join(output,'failure.html'),await page.content());
      console.error(await page.evaluate(()=>({body:document.body.innerText,saved:window.qa?.saved,calls:window.qa?.apiCalls})));
    }
  }
  if(browser)await browser.close();
  child.stdin.end();lines.close();
  let timeout;const stopped=await Promise.race([exited,new Promise(resolve=>{timeout=setTimeout(()=>resolve(null),15000);})]);
  clearTimeout(timeout);
  if(!stopped){child.kill();await exited;throw Error('Fixture required termination after cleanup timeout');}
  fs.writeFileSync(path.join(output,'server.log'),stderr);
  if(stopped.code!==0)throw Error(`Fixture cleanup failed: ${stopped.code}`);
  if(!finished)console.error('Browser checks incomplete; isolated server closed.');
}
