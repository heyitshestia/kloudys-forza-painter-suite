import {previewQuality} from './preview-quality.mjs';

export function hasMasks(shapes) { return shapes.some(shape=>shape.mask===true||shape.data?.[6]===1); }
export function maskImageCount(images) { return [...images.values()].filter(image=>image.maskCoverage).length; }
export function closeVinylPreview(image) { image?.maskCoverage?.close();image?.close(); }

export async function decodeVinylPreview(result,quality,masked) {
  const [width,height]=previewQuality(quality).size;
  const decode=async value=>{
    if(typeof value!=='string'||!value.startsWith('data:image/png;base64,'))throw Error('The vinyl preview is invalid.');
    const bytes=Uint8Array.from(atob(value.slice('data:image/png;base64,'.length)),char=>char.charCodeAt(0));
    const image=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
    if(image.width!==width||image.height!==height){image.close();throw Error('The vinyl preview has unexpected dimensions.');}
    return image;
  };
  const image=await decode(result.png);
  try {
    image.artworkBounds=result.bounds;
    if(masked){
      if(result.mask_compositing!=='ordered-section-v1')throw Error('The vinyl preview is invalid.');
      image.maskCoverage=await decode(result.mask_coverage_png);
      image.artworkBounds=result.mask_bounds;
    }
    return image;
  }catch(error){closeVinylPreview(image);throw error;}
}

export function drawVinylPreview(ctx,image) {
  if(!image.maskCoverage){ctx.drawImage(image,-1024,-512,2048,1024);return;}
  // Premultiplied result = C + (1-coverage)*destination. A transparent PNG
  // alone would incorrectly reveal the earlier vinyl instead of cutting it out.
  ctx.save();
  try {
    ctx.globalCompositeOperation='destination-out';
    ctx.drawImage(image.maskCoverage,-1024,-512,2048,1024);
    ctx.globalCompositeOperation='lighter';
    ctx.drawImage(image,-1024,-512,2048,1024);
  }finally{ctx.restore();}
}
