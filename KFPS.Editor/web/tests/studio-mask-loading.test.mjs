import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as THREE from '../../../tools/livery-inspector/vendor/three/build/three.module.min.js';

const source=readFileSync(new URL('../../../tools/livery-studio/src/web/livery-scene.js',import.meta.url),'utf8');
function harness({size=[2,1],maximum=4096,response}={}) {
  const calls=[],textures=new Set(),abort=new AbortController();
  const ctx=vm.createContext({THREE,Uint8Array,DataView,ArrayBuffer,
    renderContract:{mask_size:size},renderer:{capabilities:{maxTextureSize:maximum}},
    viewerDisposed:false,loadAbort:abort,trackedTextures:textures,
    trackTexture:t=>{textures.add(t);return t;},
    fetch:async(url,options)=>{
      calls.push({url,options});
      const bytes=new Uint8Array(16);
      const view=new DataView(bytes.buffer);view.setUint32(0,2,true);view.setUint32(4,1,true);
      bytes.set([231,123,19,0,7,8,9,255],8);
      return response?.(bytes)??{ok:true,headers:{get:()=>String(bytes.byteLength)},arrayBuffer:async()=>bytes.buffer};
    }});
  const first=source.indexOf('async function loadSurfaceMask(');
  const last=source.indexOf('async function qualifiedNativeTexture(',first);
  assert.ok(first>=0&&last>first,'The real shared mask loader must be present');
  vm.runInContext(source.slice(first,last),ctx);
  return {ctx,calls,textures,abort};
}

test('one raw mask allocation supplies picking and the unchanged filtered GPU texture',async()=>{
  const {ctx,calls,textures,abort}=harness();
  const page=await ctx.loadSurfaceMask(0),texture=ctx.surfaceMaskTexture(page);
  assert.deepEqual([...page.data],[231,123,19,0,7,8,9,255]);
  assert.equal(texture.image.data,page.data);
  assert.equal(texture.image.width,2);assert.equal(texture.image.height,1);
  assert.equal(texture.isDataTexture,true);assert.equal(textures.size,1);
  assert.equal(texture.colorSpace,THREE.NoColorSpace);assert.equal(texture.flipY,false);
  assert.equal(texture.generateMipmaps,true);assert.equal(texture.premultiplyAlpha,false);
  assert.equal(texture.minFilter,THREE.LinearMipmapLinearFilter);
  assert.equal(texture.magFilter,THREE.LinearFilter);
  assert.equal(texture.wrapS,THREE.ClampToEdgeWrapping);assert.equal(texture.wrapT,THREE.ClampToEdgeWrapping);
  assert.equal(texture.anisotropy,1);
  assert.equal(calls[0].url,'./api/local-render/mask-raw/0');
  assert.equal(calls[0].options.signal,abort.signal);
});

test('both viewers use one shared raw request per mask, without duplicate PNG decoding',()=>{
  const start=source.indexOf('async function loadPackage()'),end=source.indexOf('function resetView()',start);
  const code=source.slice(start,end);
  assert.match(code,/\[0, 1, 2\]\.map\(loadSurfaceMask\)/);
  assert.doesNotMatch(code,/loadTexture\('\.\/api\/local-render\/mask\//);
  assert.match(code,/surfaceMaskPages = maskPages/);
  assert.match(code,/maskPages\.map\(surfaceMaskTexture\)/);
});

for(const size of [[0,1],[-1,1],[2.5,1],[2,Infinity],[4097,1],[],[2,1,1]]) {
  test(`invalid or oversized native mask dimensions are rejected before allocation: ${JSON.stringify(size)}`,async()=>{
    const {ctx,calls}=harness({size});
    await assert.rejects(ctx.loadSurfaceMask(0),/mask|resolution/i);
    assert.equal(calls.length,0);
  });
}

test('wrong declared content length is rejected before reading the body',async()=>{
  let read=false;
  const {ctx}=harness({response:bytes=>({ok:true,headers:{get:()=>String(bytes.length+1)},
    arrayBuffer:async()=>{read=true;return bytes.buffer;}})});
  await assert.rejects(ctx.loadSurfaceMask(0),/length/i);assert.equal(read,false);
});

for(const problem of ['short','long','width','height']) {
  test(`corrupt native mask ${problem} is rejected`,async()=>{
    const {ctx}=harness({response:bytes=>{
      let body=bytes.buffer;
      if(problem==='short')body=body.slice(0,body.byteLength-1);
      if(problem==='long'){const larger=new Uint8Array(17);larger.set(bytes);body=larger.buffer;}
      if(problem==='width'||problem==='height')new DataView(body).setUint32(problem==='width'?0:4,3,true);
      return {ok:true,headers:{get:()=>String(bytes.length)},arrayBuffer:async()=>body};
    }});
    await assert.rejects(ctx.loadSurfaceMask(0),/dimensions|length/i);
  });
}

test('a closed viewer rejects masks before any request',async()=>{
  const {ctx,calls,textures}=harness();ctx.viewerDisposed=true;
  await assert.rejects(ctx.loadSurfaceMask(0),/closed/i);
  assert.equal(textures.size,0);assert.equal(calls.length,0);
});

test('disposal during a body read rejects the late result without allocating textures',async()=>{
  let finish,reading;
  const started=new Promise(resolve=>{reading=resolve;});
  const {ctx,textures}=harness({response:bytes=>({ok:true,headers:{get:()=>String(bytes.length)},
    arrayBuffer:()=>{reading();return new Promise(resolve=>{finish=()=>resolve(bytes.buffer);});}})});
  const pending=ctx.loadSurfaceMask(0);
  await started;ctx.viewerDisposed=true;finish();
  await assert.rejects(pending,/closed/i);assert.equal(textures.size,0);
});

test('disposal between load and adoption does not publish a GPU texture',async()=>{
  const {ctx,textures}=harness(),page=await ctx.loadSurfaceMask(0);
  ctx.viewerDisposed=true;
  assert.throws(()=>ctx.surfaceMaskTexture(page),/closed/i);assert.equal(textures.size,0);
});

test('a failed sibling mask never publishes a partial mask texture set',async()=>{
  let count=0;
  const {ctx,textures}=harness({response:bytes=>++count===2?{ok:false,status:500}
    :{ok:true,headers:{get:()=>String(bytes.length)},arrayBuffer:async()=>bytes.buffer}});
  await assert.rejects(Promise.all([0,1,2].map(index=>ctx.loadSurfaceMask(index))),/unavailable/i);
  assert.equal(textures.size,0);
});

test('network failure remains an explicit missing-mask failure',async()=>{
  const {ctx}=harness({response:()=>({ok:false,status:404})});
  await assert.rejects(ctx.loadSurfaceMask(0),/mask pixels.*unavailable/i);
});
