import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source=readFileSync(new URL('../../../tools/livery-studio/src/web/livery-editor.mjs',import.meta.url),'utf8');
const scene=readFileSync(new URL('../../../tools/livery-studio/src/web/livery-scene.js',import.meta.url),'utf8');
function between(text,start,end) {
  const first=text.indexOf(start),last=text.indexOf(end,first+start.length);
  assert.ok(first>=0&&last>first,`Missing product function: ${start}`);
  return text.slice(first,last);
}
function harness(extra={}) {
  const timers=new Map();let serial=0,now=100000;
  const c=vm.createContext({document:{hidden:true},disposed:false,busy:false,config:{},
    inactivePreviewTimer:null,previewCachesReleased:false,queued:7,previewExpiresAt:0,lastPreviewVisibleAt:-Infinity,
    inactivePreviewBudget:96*1024*1024,Date:{now:()=>now},dirtySections:new Set(),
    sectionCanvases:new Map([['Left',{width:2048,height:1024}]]),sectionCanvas:{width:2048,height:1024},
    atlas:{width:2048,height:892},images:new Map([['source',{}]]),activeQuality:'balanced',
    setTimeout:(fn,ms)=>{timers.set(++serial,{fn,due:now+ms});return serial;},clearTimeout:id=>timers.delete(id),
    cancelAnimationFrame(){},previewQuality:()=>({size:[2048,1024]}),markAll(){c.marks++;},schedule(){c.schedules++;},marks:0,schedules:0,...extra});
  vm.runInContext(between(source,'function trimInactivePreview()','function drawSection('),c);
  return {c,tick(ms=5000){now+=ms;for(const [id,timer] of [...timers])if(timer.due<=now){timers.delete(id);timer.fn();}},timers};
}
test('inactive Studio keeps small caches warm, then expires without touching sources or quality',()=>{
  const {c,tick}=harness();const atlas=c.atlas,images=c.images,section=c.sectionCanvases.get('Left');
  c.handlePreviewVisibility();assert.equal(c.sectionCanvases.size,1);tick();
  assert.equal(c.sectionCanvases.size,1);assert.equal(c.sectionCanvas.width,2048);
  tick(25000);
  assert.equal(c.sectionCanvases.size,0);assert.equal(section.width,1);assert.equal(c.sectionCanvas.width,1);
  assert.equal(c.atlas,atlas);assert.equal(c.images,images);assert.equal(images.size,1);
  c.document.hidden=false;c.handlePreviewVisibility();
  assert.equal(c.sectionCanvas.width,2048);assert.equal(c.sectionCanvas.height,1024);assert.equal(c.schedules,1);
  assert.deepEqual([...c.dirtySections],['Left']);
});

test('Studio trims largest sections to its budget and only marks retired sections dirty',()=>{
  const {c,tick}=harness({inactivePreviewBudget:32*1024*1024});
  c.sectionCanvases.set('Large',{width:4096,height:4096});
  c.handlePreviewVisibility();tick();
  assert.equal(c.sectionCanvases.has('Large'),false);assert.equal(c.sectionCanvases.has('Left'),true);
  assert.deepEqual([...c.dirtySections],['Large']);
  assert.equal(c.sectionCanvas.width,2048);
  c.document.hidden=false;c.handlePreviewVisibility();assert.equal(c.marks,0);assert.equal(c.schedules,1);
});

test('recently revisited Studio retains its bounded caches for sixty seconds',()=>{
  const {c,tick}=harness();
  c.handlePreviewVisibility();tick();c.document.hidden=false;c.handlePreviewVisibility();
  c.document.hidden=true;c.handlePreviewVisibility();tick(30000);
  assert.equal(c.sectionCanvases.size,1);tick(30000);assert.equal(c.sectionCanvases.size,0);
});

test('delayed or busy cleanup respects expiry and preserves already dirty sections',()=>{
  const {c,tick,timers}=harness();c.dirtySections.add('Right');
  c.handlePreviewVisibility();c.busy=true;tick(90000);
  assert.equal(c.sectionCanvases.size,1);c.busy=false;tick();
  assert.equal(c.sectionCanvases.size,0);assert.equal(timers.size,0);
  assert.deepEqual([...c.dirtySections],['Right','Left']);
});
test('rapid switches and async quality operations cannot retire live previews',()=>{
  const {c,tick,timers}=harness();
  for(let i=0;i<20;i++){c.document.hidden=true;c.handlePreviewVisibility();c.document.hidden=false;c.handlePreviewVisibility();}
  tick();assert.equal(c.sectionCanvases.size,1);assert.equal(timers.size,0);
  c.document.hidden=true;c.busy=true;c.handlePreviewVisibility();tick();assert.equal(c.sectionCanvases.size,1);
  c.busy=false;tick(60000);assert.equal(c.sectionCanvases.size,0);
  c.disposed=true;c.document.hidden=false;c.handlePreviewVisibility();assert.equal(c.marks,0);
});
test('inactive viewer retires its framebuffer without releasing model or WebGL context',()=>{
  const timers=new Map(),sizes=[];let serial=0,resizes=0,requests=0;
  const c=vm.createContext({document:{hidden:true},viewerDisposed:false,lastFrameAt:3,animationFrameId:7,
    inactiveFramebufferTimer:null,framebufferTrimmed:false,cancelAnimationFrame(){},
    setTimeout:fn=>{timers.set(++serial,fn);return serial;},clearTimeout:id=>timers.delete(id),
    renderer:{setPixelRatio(){},setSize:(...args)=>sizes.push(args)},resize(){resizes++;},requestRender(){requests++;}});
  vm.runInContext(between(scene,'function handleVisibilityChange()','function releaseRendererContext()'),c);
  c.handleVisibilityChange();assert.equal(c.animationFrameId,0);
  [...timers.values()].forEach(f=>f());assert.equal(c.framebufferTrimmed,true);assert.deepEqual(sizes,[[1,1,false]]);
  c.document.hidden=false;c.handleVisibilityChange();assert.equal(resizes,1);assert.equal(requests,1);
});
