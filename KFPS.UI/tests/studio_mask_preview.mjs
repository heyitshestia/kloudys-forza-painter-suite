import test from 'node:test';
import assert from 'node:assert/strict';
import {hasMasks,maskImageCount,closeVinylPreview,decodeVinylPreview,drawVinylPreview} from '../../tools/livery-studio/src/web/vinyl-compositing.mjs';
import {previewFootprint,checkPreviewQuality} from '../../tools/livery-studio/src/web/preview-quality.mjs';

const png='data:image/png;base64,AA==';
const result=()=>({png,bounds:[1,2,3,4],mask_compositing:'ordered-section-v1',mask_coverage_png:png,mask_bounds:[0,0,10,10]});
const bitmap=(width=1024,height=512)=>({width,height,closed:0,close(){this.closed++;}});

test('mask detection and retained bitmap counting',()=>{
  assert.equal(hasMasks([{mask:false,data:[0,0,1,1,0,0,0]}]),false);
  assert.equal(hasMasks([{mask:true}]),true);
  assert.equal(hasMasks([{data:[0,0,1,1,0,0,1]}]),true);
  assert.equal(maskImageCount(new Map([['a',{}],['b',{maskCoverage:{}}]])),1);
});

test('unmasked previews retain original picking bounds and one allocation',async()=>{
  const image=bitmap();let calls=0;
  globalThis.createImageBitmap=async()=>{calls++;return image;};
  const decoded=await decodeVinylPreview(result(),'fast',false);
  assert.equal(decoded,image);assert.equal(calls,1);
  assert.deepEqual(decoded.artworkBounds,[1,2,3,4]);
  closeVinylPreview(decoded);assert.equal(image.closed,1);
});

test('masked previews include cutout bounds and dispose both bitmaps',async()=>{
  const images=[bitmap(),bitmap()],queue=[...images];
  globalThis.createImageBitmap=async()=>queue.shift();
  const decoded=await decodeVinylPreview({...result(),bounds:null},'fast',true);
  assert.deepEqual(decoded.artworkBounds,[0,0,10,10]);
  closeVinylPreview(decoded);
  assert.deepEqual(images.map(v=>v.closed),[1,1]);
});

test('missing or unsupported mask payload releases the color image',async()=>{
  for(const changes of [{mask_compositing:null},{mask_coverage_png:null},{mask_coverage_png:'invalid'}]){
    const image=bitmap();globalThis.createImageBitmap=async()=>image;
    await assert.rejects(decodeVinylPreview({...result(),...changes},'fast',true));
    assert.equal(image.closed,1);
  }
});

test('decode failures and wrong dimensions do not leak bitmaps',async()=>{
  for(const failAt of [1,2]){
    const images=[bitmap(),bitmap()];images[failAt-1].width=1;
    const queue=[...images];globalThis.createImageBitmap=async()=>queue.shift();
    await assert.rejects(decodeVinylPreview(result(),'fast',true),/dimensions/);
    assert.deepEqual(images.map(v=>v.closed),failAt===1?[1,0]:[1,1]);
  }
  const image=bitmap();let calls=0;
  globalThis.createImageBitmap=async()=>{if(calls++)throw Error('decode failed');return image;};
  await assert.rejects(decodeVinylPreview(result(),'fast',true),/decode failed/);
  assert.equal(image.closed,1);
});

test('invalid color PNG fails before allocation',async()=>{
  globalThis.createImageBitmap=async()=>{throw Error('must not decode');};
  await assert.rejects(decodeVinylPreview({png:null},'fast',false),/preview is invalid/);
});

test('masked drawing erases then adds without changing opacity or caller state',()=>{
  const image={maskCoverage:{}},calls=[];
  const ctx={globalAlpha:.5,globalCompositeOperation:'source-over',
    save(){this.previous=this.globalCompositeOperation;},
    restore(){this.globalCompositeOperation=this.previous;},
    drawImage(value,...args){calls.push([value,this.globalCompositeOperation,this.globalAlpha,args]);}};
  drawVinylPreview(ctx,image);
  assert.deepEqual(calls,[[image.maskCoverage,'destination-out',.5,[-1024,-512,2048,1024]],
                          [image,'lighter',.5,[-1024,-512,2048,1024]]]);
  assert.equal(ctx.globalCompositeOperation,'source-over');
  calls.length=0;drawVinylPreview(ctx,{});
  assert.equal(calls.length,1);assert.equal(calls[0][1],'source-over');
});

test('drawing failure still restores compositing state',()=>{
  let restored=false;
  const ctx={save(){},restore(){restored=true;},drawImage(){throw Error('lost bitmap');}};
  assert.throws(()=>drawVinylPreview(ctx,{maskCoverage:{}}),/lost bitmap/);
  assert.equal(restored,true);
});

test('mask allocations participate in steady and staged memory gates',()=>{
  const options={quality:'balanced',paintSize:[2048,1024],sources:2,sections:1};
  const before=previewFootprint(options),after=previewFootprint({...options,masks:1});
  assert.equal(after.cpu-before.cpu,2*2048*1024*4);
  assert.equal(after.canvasGpu-before.canvasGpu,2048*1024*4);
  assert.equal(after.webglGpu,before.webglGpu);
  const budget={maxTextureSize:8192,sceneBytes:0,gpuBudget:before.gpu,cpuBudget:2**30};
  assert.equal(checkPreviewQuality({...options,...budget}).allowed,true);
  assert.equal(checkPreviewQuality({...options,...budget,masks:1}).reason,'gpu');
  const staged=checkPreviewQuality({...options,...budget,masks:1,current:before});
  assert.equal(staged.peakCpu,after.cpu+before.cpu);
  assert.equal(staged.peakGpu,after.gpu+before.canvasGpu);
  for(const masks of [-1,3,.5,NaN,'1'])assert.throws(()=>previewFootprint({...options,masks}),/allocation/);
});
