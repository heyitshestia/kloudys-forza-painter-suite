import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {studioTourSteps} from '../src/web/studio-tour.mjs';
import en from '../src/web/locales/en.mjs';
import ko from '../src/web/locales/ko.mjs';
import ja from '../src/web/locales/ja.mjs';
import {PALETTES} from '../src/web/theme-adapter.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const web=path.join(root,'tools/livery-studio/src/web'),output=path.join(root,'runtime/studio-completion-20261111/tour/browser');
fs.mkdirSync(output,{recursive:true});
for(const step of studioTourSteps)for(const key of [step.title,step.body]){
  assert.equal(en[key],key);assert(ko[key]&&ko[key]!==key);assert(ja[key]&&ja[key]!==key);
}
const require=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium}=require('playwright');
const server=http.createServer((request,response)=>{
  const pathname=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
  const file=path.resolve(web,'.'+(pathname==='/'?'/index.html':pathname));
  if(!file.startsWith(web+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){response.writeHead(404).end();return;}
  response.setHeader('Content-Type',/\.(mjs|js)$/.test(file)?'application/javascript':file.endsWith('.css')?'text/css':'text/html');
  response.end(fs.readFileSync(file));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const results=[];let browser;
try{
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--disable-gpu','--disable-software-rasterizer'],env:{...process.env,TEMP:output,TMP:output}});
  const cases=[['en',1440,900,'dark'],['ko',1024,768,'dark'],['ja',390,844,'dark'],['en',640,360,'dark'],['ko',320,480,'dark'],['ja',640,320,'dark'],
    ...Object.keys(PALETTES).filter(name=>name!=='dark').map(name=>['en',1280,720,name])];
  for(const [language,width,height,theme] of cases){
    const page=await browser.newPage({viewport:{width,height},reducedMotion:'reduce'}),errors=[];
    page.on('pageerror',error=>errors.push(String(error)));
    await page.addInitScript(()=>{
      const Native=window.ResizeObserver,targets=new Map();
      window.ResizeObserver=class extends Native{
        constructor(callback){super(callback);targets.set(this,new Set());}
        observe(node,options){targets.get(this).add(node);return super.observe(node,options);}
        unobserve(node){targets.get(this).delete(node);return super.unobserve(node);}
        disconnect(){targets.get(this).clear();return super.disconnect();}
      };
      window.__observedTourTargets=()=>[...targets.values()].reduce((n,set)=>n+set.size,0);
    });
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.origin!==`http://127.0.0.1:${server.address().port}`)return route.abort();
      const pathname=url.pathname;
      if(pathname==='/api/language')return route.fulfill({json:{language}});
      if(pathname.endsWith('/theme-adapter.mjs'))return route.fulfill({contentType:'application/javascript',body:`export async function initializeTheme(){
        for(const [key,value] of Object.entries(${JSON.stringify(PALETTES[theme])}))document.documentElement.style.setProperty(key,value);
        document.documentElement.dataset.editorThemeBase=${JSON.stringify(theme)};
        document.documentElement.removeAttribute('data-theme-loading');}`});
      if(pathname.endsWith('/livery-editor.mjs'))return route.fulfill({contentType:'application/javascript',body:`
        import {initializeStudioTools} from './studio-tools.mjs';
        import {initializeWorkspacePanels} from './workspace-panels.mjs';
        import {initializeStudioTour} from './studio-tour.mjs';
        initializeStudioTools({state:()=>({project:{vinyls:[],placements:[]},selectedIds:[]}),action(){},message(){}});
        for(const id of ['inspectionToolsHost','recoveryToolsHost'])document.getElementById(id).textContent='Fixture controls';
        document.getElementById('placementList').textContent='Fixture placement';
        let busy=false;const panels=initializeWorkspacePanels({canLeave:()=>!busy});
        const tour=initializeStudioTour({panels,canStart:()=>!busy,message:text=>window.__tourMessage=text});
        window.__tourTest={tour,panels,busy:value=>{busy=value;}};
      `});
      if(/\/(release-announcement|activity-client)\.js$/.test(pathname))return route.fulfill({contentType:'application/javascript',body:''});
      return route.continue();
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>window.__tourTest);
    assert.equal(await page.locator('#studioTour').isVisible(),false,'Tour must not auto-open');
    await page.evaluate(()=>{
      __tourTest.panels.show('design',{force:true});
      document.getElementById('inspectorBody').scrollTop=140;
      document.getElementById('sourcePanel').open=false;
    });
    const before=await page.evaluate(()=>({tab:document.querySelector('[aria-selected=true][data-inspector-tab]').dataset.inspectorTab,
      top:document.getElementById('inspectorBody').scrollTop,preference:sessionStorage.getItem('kfps.studio.inspector.v1')}));
    await page.locator('#showStudioTour').click();
    const pack={en,ko,ja}[language];
    for(const [i,step] of studioTourSteps.entries()){
      assert.equal(await page.locator('#studioTour').getAttribute('data-step'),step.id);
      assert.equal(await page.locator('#studioTourTitle').textContent(),pack[step.title]);
      assert.equal(await page.evaluate(()=>sessionStorage.getItem('kfps.studio.inspector.v1')),before.preference,'Tour persisted its temporary panel');
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
      const layout=await page.evaluate(()=>{
        const c=document.querySelector('.studio-tour-card'),r=c.getBoundingClientRect();
        const hit=document.elementFromPoint(r.left+20,r.top+20);
        return {inside:r.left>=0&&r.top>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1,
          onTop:c.contains(hit),overflow:c.scrollWidth>c.clientWidth+1,modal:document.getElementById('studioTour').matches(':modal'),
          transparent:getComputedStyle(document.getElementById('studioTour')).backgroundColor==='rgba(0, 0, 0, 0)'};
      });
      assert.deepEqual(layout,{inside:true,onTop:true,overflow:false,modal:true,transparent:true},`${language}/${theme}/${step.id}`);
      if(['car','inspection','export'].includes(step.id))await page.screenshot({path:path.join(output,`${language}-${width}-${theme.replace(':','-')}-${step.id}.png`)});
      await page.locator('[data-tour-next]').click();
    }
    assert.equal(await page.locator('#studioTour').isVisible(),false);
    assert.deepEqual(await page.evaluate(()=>({tab:document.querySelector('[aria-selected=true][data-inspector-tab]').dataset.inspectorTab,
      top:document.getElementById('inspectorBody').scrollTop,preference:sessionStorage.getItem('kfps.studio.inspector.v1')})),before);
    assert.equal(await page.locator('#sourcePanel').evaluate(node=>node.open),false);
    assert.equal(await page.evaluate(()=>__observedTourTargets()),0,'Closed tour kept observing layout');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'showStudioTour');
    await page.locator('#showStudioTour').click();await page.locator('[data-tour-next]').click();await page.locator('[data-tour-back]').click();
    assert.equal(await page.locator('[data-tour-back]').isDisabled(),true);
    for(let n=0;n<6;n++){
      await page.keyboard.press('Tab');assert(await page.evaluate(()=>document.getElementById('studioTour').contains(document.activeElement)));
    }

    // Navigation keys remain local; browser Save and app mutations are suppressed.
    const keyboard=await page.evaluate(()=>{
      let leaked=0;const handler=()=>leaked++;window.addEventListener('keydown',handler);
      const target=document.querySelector('[data-tour-next]');
      const save=new KeyboardEvent('keydown',{bubbles:true,cancelable:true,ctrlKey:true,code:'KeyS',key:'s'});
      target.dispatchEvent(save);
      target.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,cancelable:true,code:'Delete',key:'Delete'}));
      window.removeEventListener('keydown',handler);
      return {leaked,savePrevented:save.defaultPrevented};
    });
    assert.deepEqual(keyboard,{leaked:0,savePrevented:true});
    for(let n=0;n<6;n++){
      await page.keyboard.press('Shift+Tab');assert(await page.evaluate(()=>document.getElementById('studioTour').contains(document.activeElement)));
    }
    await page.keyboard.press('Escape');assert.equal(await page.locator('#studioTour').isVisible(),false);
    await page.evaluate(()=>__tourTest.busy(true));await page.locator('#showStudioTour').click();
    assert.equal(await page.locator('#studioTour').isVisible(),false);assert(await page.evaluate(()=>!!window.__tourMessage));
    await page.evaluate(()=>{__tourTest.busy(false);document.getElementById('shortcuts').showModal();});
    assert.equal(await page.evaluate(()=>__tourTest.tour.open()),false);await page.evaluate(()=>document.getElementById('shortcuts').close());
    // Missing controls, unavailable browser storage and rapid replay must all be safe.
    await page.evaluate(()=>{
      document.getElementById('chooseCar').remove();
      Object.defineProperty(window,'sessionStorage',{configurable:true,get(){throw Error('Storage unavailable');}});
      __tourTest.tour.open();__tourTest.tour.close();__tourTest.tour.open();
    });
    assert.equal(await page.locator('#studioTour').getAttribute('data-step'),'car');
    assert(await page.locator('#studioTour').evaluate(node=>node.classList.contains('without-target')));
    await page.locator('[data-tour-next]').click();
    assert.equal(await page.locator('.studio-tour-spotlight').isVisible(),true);
    await page.setViewportSize({width:320,height:480});
    await page.locator('[data-tour-close]').click();
    await page.evaluate(()=>{__tourTest.tour.open();__tourTest.tour.dispose();__tourTest.tour.dispose();});assert.equal(await page.locator('#studioTour').count(),0);
    assert.equal(await page.locator('#showStudioTour').isDisabled(),true);
    assert.equal(await page.evaluate(()=>__tourTest.tour.open()),false,'Disposed tour reopened');
    await page.evaluate(async()=>{
      const {initializeStudioTour}=await import('./studio-tour.mjs');
      const tour=initializeStudioTour({panels:__tourTest.panels});
      tour.open();tour.close();tour.dispose();
    });
    assert.equal(await page.locator('#studioTour').count(),0,'Remount cleanup failed');
    assert.equal(await page.evaluate(()=>__observedTourTargets()),0,'Disposed tour kept observing layout');
    assert.deepEqual(errors,[]);
    results.push({language,width,height,theme,steps:studioTourSteps.length,passed:true});await page.close();
  }
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
