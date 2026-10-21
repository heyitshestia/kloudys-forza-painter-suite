// Preview pixels only. Layout, picking and save coordinates stay 2048 x 1024.
const levels=Object.freeze({
  fast:Object.freeze({scale:.5,size:Object.freeze([1024,512])}),
  balanced:Object.freeze({scale:1,size:Object.freeze([2048,1024])}),
  sharp:Object.freeze({scale:2,size:Object.freeze([4096,2048])}),
});
export function previewQuality(value='balanced') {
  if(typeof value!=='string'||!Object.hasOwn(levels,value))throw Error('Invalid vinyl preview quality.');
  return levels[value];
}
export function scaledTransform(matrix,scale) { return matrix.map(value=>value*scale); }
export function previewFootprint({quality,paintSize,sources,sections}) {
  const {scale,size}=previewQuality(quality);
  if(!Array.isArray(paintSize)||paintSize.length!==2||!paintSize.every(value=>Number.isSafeInteger(value)&&value>0&&value<=32768)
    ||!Number.isSafeInteger(sources)||sources<0||sources>96||!Number.isSafeInteger(sections)||sections<0||sections>11)
    throw Error('Invalid preview allocation.');
  const paint=paintSize.map(value=>Math.ceil(value*scale)),plane=size[0]*size[1]*4,atlas=paint[0]*paint[1]*4;
  // Include decoded/encoded source images, section display, render/decode scratch,
  // retained undo sources and mipmapped GPU paint. Callers add old live buffers.
  const webglGpu=Math.ceil(atlas*4/3),canvasGpu=atlas+plane*(sources+sections+1);
  return {paint,size:[...size],cpu:atlas+plane*(2*sources+sections+4),gpu:webglGpu+canvasGpu,webglGpu,canvasGpu};
}
export function checkPreviewQuality({maxTextureSize,sceneBytes,gpuBudget,cpuBudget,current,...options}) {
  const footprint=previewFootprint(options),peakCpu=footprint.cpu+(current?.cpu||0);
  const peakGpu=sceneBytes+footprint.gpu+(current?.canvasGpu||0);
  const reason=![maxTextureSize,sceneBytes,gpuBudget,cpuBudget].every(Number.isFinite)?'memory'
    :Math.max(...footprint.paint,...footprint.size)>maxTextureSize?'texture'
    :peakGpu>gpuBudget?'gpu':peakCpu>cpuBudget?'memory':null;
  return {...footprint,peakCpu,peakGpu,allowed:reason===null,reason};
}
