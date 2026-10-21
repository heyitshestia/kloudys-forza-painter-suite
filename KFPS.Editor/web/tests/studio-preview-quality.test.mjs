import test from 'node:test';
import assert from 'node:assert/strict';
import { previewQuality, previewFootprint, checkPreviewQuality, scaledTransform } from '../../../tools/livery-studio/src/web/preview-quality.mjs';
import {placementMatrix,sectionToPaint,mapPoint} from '../../../tools/livery-studio/src/web/layout-model.mjs';

const MiB=1024**2;
test('allowlisted sizes, balanced default and unchanged logical transforms',()=>{
  assert.deepEqual(['fast','balanced','sharp'].map(key=>previewQuality(key).size),[[1024,512],[2048,1024],[4096,2048]]);
  for(const key of [null,1,'__proto__','constructor','4k'])assert.throws(()=>previewQuality(key));
  assert.equal(previewQuality().scale,1);
  assert.deepEqual(scaledTransform([1,2,3,4,5,6],2),[2,4,6,8,10,12]);
});
test('memory includes history images, sections, atlas, staging and GPU mipmaps',()=>{
  const base=previewFootprint({quality:'balanced',paintSize:[2048,2048],sources:4,sections:11});
  const sharp=previewFootprint({quality:'sharp',paintSize:[2048,2048],sources:4,sections:11});
  assert.equal(sharp.cpu,base.cpu*4);assert.ok(Math.abs(sharp.gpu-base.gpu*4)<4);
  assert.ok(base.cpu>4*2048*1024*4+11*2048*1024*4);
  const args={quality:'sharp',paintSize:[2048,2048],sources:4,sections:11,maxTextureSize:8192,sceneBytes:64*MiB,gpuBudget:1024*MiB,cpuBudget:1024*MiB,current:base};
  assert.equal(checkPreviewQuality(args).allowed,true);
  assert.equal(checkPreviewQuality({...args,maxTextureSize:2048}).reason,'texture');
  assert.equal(checkPreviewQuality({...args,gpuBudget:80*MiB}).reason,'gpu');
  assert.equal(checkPreviewQuality({...args,cpuBudget:128*MiB}).reason,'memory');
  assert.equal(checkPreviewQuality({...args,gpuBudget:512*MiB}).reason,'gpu');
  const checked=checkPreviewQuality(args);
  assert.ok(checked.peakCpu>=sharp.cpu+base.cpu);assert.ok(checked.peakGpu>=sharp.gpu+args.sceneBytes);
});
test('invalid dimensions and unbounded allocation counts are rejected',()=>{
  for(const paintSize of [[0,2048],[Infinity,2048],[2048],[-1,2048],[2048.5,1024]])assert.throws(()=>previewFootprint({quality:'sharp',paintSize,sources:1,sections:11}));
  for(const sources of [-1,Infinity,100000,0.5])assert.throws(()=>previewFootprint({quality:'sharp',paintSize:[2048,2048],sources,sections:11}));
});
test('all preview sizes preserve normalized atlas placement for rotated/skewed artwork',()=>{
  const paintSize=[2048,892],section={atlasToLocal:[0,-1,2048,1,0,0],source_region:[.1,.2,.8,.9],paint_region:[.2,.1,.7,.6]};
  const placement={x:38.123456789,y:-22.987654321,scaleX:1.3,scaleY:.6,rotation:37,skew:.45};
  const input=JSON.stringify({section,placement});
  for(const point of [[-300,-100],[0,0],[200,350]]){
    const local=mapPoint(placementMatrix(placement),...point);
    const normal=mapPoint(sectionToPaint(section,paintSize),...local).map((value,i)=>value/paintSize[i]);
    for(const quality of ['fast','balanced','sharp']){
      const {paint}=previewFootprint({quality,paintSize,sources:1,sections:10});
      const result=mapPoint(sectionToPaint(section,paint),...local).map((value,i)=>value/paint[i]);
      result.forEach((value,i)=>assert.ok(Math.abs(value-normal[i])<1e-12));
    }
  }
  assert.equal(JSON.stringify({section,placement}),input);
});
