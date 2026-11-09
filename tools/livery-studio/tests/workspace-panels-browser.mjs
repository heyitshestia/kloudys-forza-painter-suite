import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const web=path.join(root,'tools/livery-studio/src/web');
const output=path.join(root,'runtime/studio-package-workspace-20261102/panels');
fs.mkdirSync(output,{recursive:true});
const require=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json'));
const {chromium}=require('playwright');
const server=http.createServer((request,response)=>{
  const pathname=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
  const file=path.resolve(web,'.'+(pathname==='/'?'/index.html':pathname));
  if(!file.startsWith(web+path.sep)||!fs.existsSync(file)){response.writeHead(404).end();return;}
  response.setHeader('Content-Type',/\.(mjs|js)$/.test(file)?'application/javascript':file.endsWith('.css')?'text/css':'text/html');
  response.end(fs.readFileSync(file));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try {
  browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args:['--disable-gpu'],env:{...process.env}});
  const results=[];
  for(const [language,width,height] of [['en',1440,900],['ko',1024,768],['ja',390,844]]){
    const page=await browser.newPage({viewport:{width,height}}),errors=[];
    page.on('pageerror',error=>errors.push(String(error)));
    await page.route('**/*',async route=>{
      const pathname=new URL(route.request().url()).pathname;
      if(pathname==='/api/language')return route.fulfill({json:{language}});
      if(pathname.endsWith('/theme-adapter.mjs'))return route.fulfill({contentType:'application/javascript',body:'export async function initializeTheme(){document.documentElement.removeAttribute("data-theme-loading");}'});
      if(pathname.endsWith('/livery-editor.mjs'))return route.fulfill({contentType:'application/javascript',body:`
        import {initializeStudioTools} from './studio-tools.mjs';
        import {initializeWorkspacePanels} from './workspace-panels.mjs';
        const tools=initializeStudioTools({state:()=>({project:{vinyls:[],placements:[]},selectedIds:[]}),action(){},message(){}});
        document.getElementById('previewQuality').disabled=false;
        document.getElementById('groupSelection').disabled=false;
        let allowed=true;
        const panels=initializeWorkspacePanels({canLeave:()=>allowed});
        window.__panels={panels,tools,block:value=>{allowed=!value;}};
      `});
      if(/\/(release-announcement|activity-client)\.js$/.test(pathname))return route.fulfill({contentType:'application/javascript',body:''});
      return route.continue();
    });
    await page.goto(`http://127.0.0.1:${server.address().port}/`);
    await page.waitForFunction(()=>window.__panels,null,{timeout:10000});
    assert.equal(await page.locator('#inspectorTabs [role=tab]').count(),5);
    assert.equal(await page.locator('#inspector-placement').isVisible(),true);
    assert.equal(await page.locator('#selectionTools').isVisible(),true);
    for(const tab of ['design','car','view','project','placement']){
      await page.locator(`[data-inspector-tab="${tab}"]`).click();
      assert.equal(await page.locator(`#inspector-${tab}`).isVisible(),true);
      assert.equal(await page.locator('.inspector-panel:not([hidden])').count(),1);
    }
    await page.evaluate(()=>window.__panels.block(true));
    await page.locator('[data-inspector-tab=car]').click();
    assert.equal(await page.locator('#inspector-placement').isVisible(),true);
    await page.evaluate(()=>window.__panels.block(false));
    await page.evaluate(()=>{const button=document.querySelector('#exportSection');button.disabled=false;button.click();});
    assert.equal(await page.locator('#inspector-design').isVisible(),true,'Hidden command did not reveal its feedback.');
    await page.locator('[data-inspector-tab=placement]').click();
    await page.locator('[data-inspector-tab=placement]').focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('[data-inspector-tab=design]').getAttribute('aria-selected'),'true');
    await page.locator('[data-inspector-tab=car]').click();
    assert.equal(await page.locator('#componentPanel').getAttribute('open'),'');
    assert.equal(await page.locator('#parts').evaluate(node=>getComputedStyle(node).maxHeight),'none');
    await page.locator('#componentPanel > summary').click();
    assert.equal(await page.locator('#componentPanel').getAttribute('open'),'');
    await page.locator('[data-quality-choice=sharp]').click();
    assert.equal(await page.locator('#previewQuality').inputValue(),'sharp');
    assert.equal(await page.locator('[data-quality-choice=sharp]').getAttribute('aria-pressed'),'true');
    await page.evaluate(()=>document.getElementById('previewQuality').disabled=true);
    assert.equal(await page.locator('[data-quality-choice=fast]').isDisabled(),true);
    const issues=await page.evaluate(()=>{
      const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);
      const duplicates=ids.filter((id,n)=>ids.indexOf(id)!==n);
      const overflow=[...document.querySelectorAll('#inspectorTabs button,.inspector-panel button,.quality-buttons button')]
        .filter(n=>n.getClientRects().length&&n.scrollWidth>n.clientWidth+2).map(n=>n.id||n.textContent);
      return {duplicates,overflow,pageOverflow:document.documentElement.scrollWidth>innerWidth+2};
    });
    assert.deepEqual(issues,{duplicates:[],overflow:[],pageOverflow:false});
    await page.screenshot({path:path.join(output,`${language}-${width}.png`),fullPage:true});
    await page.evaluate(()=>window.__panels.panels.dispose());
    assert.equal(await page.locator('#inspectorTabs').count(),0);
    assert.equal(await page.locator('#authoring #properties').count(),1);
    assert.deepEqual(errors,[]);
    results.push({language,width,height,passed:true});
    await page.close();
  }
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));
  console.log(JSON.stringify(results));
} finally {
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
