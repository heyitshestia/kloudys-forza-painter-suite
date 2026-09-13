export const MAX_SCREENSHOTS = 3;
export const MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024;
export const MAX_SCREENSHOTS_BYTES = 10 * 1024 * 1024;
export const MAX_SCREENSHOT_PIXELS = 40 * 1000 * 1000;

export function screenshotInfo(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let type, width, height;
  if (bytes.length >= 33 && [137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v)
      && view.getUint32(8) === 13 && view.getUint32(12) === 0x49484452) {
    type = 'image/png'; width = view.getUint32(16); height = view.getUint32(20);
  } else if (bytes.length >= 4 && bytes[0]===255 && bytes[1]===216 && bytes.at(-2)===255 && bytes.at(-1)===217) {
    type = 'image/jpeg';
    let offset = 2;
    while (offset + 4 <= bytes.length) {
      if (bytes[offset++] !== 255) break;
      while (bytes[offset] === 255) offset++;
      const marker = bytes[offset++];
      if ([0xda,0xd9].includes(marker)) break;
      if (marker===1 || (marker>=0xd0 && marker<=0xd7)) continue;
      if (offset + 2 > bytes.length) break;
      const length = view.getUint16(offset);
      if (length < 2 || offset + length > bytes.length) break;
      if ([0xc0,0xc1,0xc2].includes(marker) && length >= 8) {
        height = view.getUint16(offset+3); width = view.getUint16(offset+5); break;
      }
      offset += length;
    }
  }
  if (!width || !height || width > 16384 || height > 16384 || width*height > MAX_SCREENSHOT_PIXELS) {
    throw new Error('Choose a valid PNG or JPG screenshot up to 40 megapixels (16,384 pixels per side).');
  }
  return {type,width,height};
}

export function validateScreenshotMetadata(items, confirmed) {
  if (!Array.isArray(items) || items.length > MAX_SCREENSHOTS) throw new Error('Attach no more than 3 screenshots.');
  if (items.length && confirmed !== true) throw new Error('Confirm that your screenshots will be public before sending.');
  let total = 0;
  const result = items.map(item => {
    if (!['image/png','image/jpeg'].includes(item?.type) || !Number.isSafeInteger(item.size)
        || item.size < 1 || item.size > MAX_SCREENSHOT_BYTES || !/^[a-f0-9]{64}$/.test(item.sha256 || '')
        || !Number.isSafeInteger(item.width) || !Number.isSafeInteger(item.height)
        || item.width < 1 || item.height < 1 || item.width > 16384 || item.height > 16384
        || item.width * item.height > MAX_SCREENSHOT_PIXELS) throw new Error('Invalid screenshot. Use PNG or JPG, up to 5 MiB each.');
    total += item.size;
    return {type:item.type,size:item.size,sha256:item.sha256,width:item.width,height:item.height};
  });
  if (total > MAX_SCREENSHOTS_BYTES) throw new Error('Screenshots must total 10 MiB or less.');
  return result;
}

export async function describeScreenshot(file) {
  if (!file || file.size < 1 || file.size > MAX_SCREENSHOT_BYTES) throw new Error('Each screenshot must be 5 MiB or smaller.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  const info = screenshotInfo(bytes);
  if (file.type !== info.type) throw new Error('Screenshot contents do not match PNG or JPG format.');
  const sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  return {...info,size:bytes.length,sha256};
}

export function screenshotName(index,type) { return `screenshot-${index+1}.${type==='image/png'?'png':'jpg'}`; }
