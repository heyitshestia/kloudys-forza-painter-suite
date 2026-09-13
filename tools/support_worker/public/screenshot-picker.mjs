import {MAX_SCREENSHOTS,MAX_SCREENSHOTS_BYTES,describeScreenshot,validateScreenshotMetadata,screenshotName} from './screenshots.mjs';
import {t} from './report-locale.mjs';

export class ScreenshotPicker {
  constructor({getAccount,getSubmitted,getSending,onChange,onError,onReady}) {
    Object.assign(this,{getAccount,getSubmitted,getSending,onChange,onError,onReady});
    this.items=[]; this.busy=false;
    this.input=document.getElementById('screenshots');
    this.choose=document.getElementById('choose-screenshots');
    this.choose.onclick=()=>this.input.click();
    this.preview=document.getElementById('screenshot-previews');
    this.consent=document.getElementById('screenshots-public');
    this.input.addEventListener('change',()=>{const files=Array.from(this.input.files||[]);this.input.value='';this.add(files);});
    document.addEventListener('paste',event=>{
      const files=Array.from(event.clipboardData?.files||[]).filter(file=>file.type.startsWith('image/'));
      if(!files.length || !document.getElementById('screenshots-section').getClientRects().length)return;
      event.preventDefault();this.add(files);
    });
    this.consent.addEventListener('change',()=>this.onChange());
    window.addEventListener('pagehide',()=>this.clear());
    window.addEventListener('pageshow',()=>this.refresh());
    this.refresh();
  }
  refresh() {
    this.input.disabled=this.busy || this.getSending() || !this.getAccount()?.authenticated;
    this.choose.disabled=this.input.disabled;
    document.getElementById('screenshot-state').textContent=t(!this.getAccount()?.authenticated
      ? 'Sign in before adding screenshots.'
      : this.busy ? 'Preparing screenshot previews...'
      : this.getSubmitted()?.screenshots?.length && !this.items.length
        ? 'To retry, reattach the same screenshots in the original order. No images are silently left out.'
        : 'Optional. PNG/JPG only, up to 3 images, 5 MiB each and 10 MiB total. Images stay in this tab until you send; after a reload, select them again.');
    this.consent.disabled=this.busy || !!this.getSubmitted();
    if(this.getSubmitted()?.screenshots?.length) this.consent.checked=true;
    this.preview.replaceChildren(...this.items.map((item,i)=>{
      const figure=document.createElement('figure'),link=document.createElement('a'),img=document.createElement('img');
      link.href=item.url; link.target='_blank'; link.rel='noopener'; link.title=t('Open screenshot {0} preview',i+1);
      img.src=item.url; img.alt=t('Public screenshot {0} preview',i+1); link.append(img);
      const caption=document.createElement('figcaption');
      caption.textContent=t('Screenshot {0} ({1} x {2})',i+1,item.metadata.width,item.metadata.height);
      const remove=document.createElement('button'); remove.type='button'; remove.textContent=t('Remove');
      remove.setAttribute('aria-label',t('Remove screenshot {0}',i+1)); remove.disabled=this.busy||this.getSending();
      remove.onclick=()=>{URL.revokeObjectURL(item.url);this.items.splice(i,1);if(!this.getSubmitted())this.consent.checked=false;this.refresh();this.onChange();};
      figure.append(link,caption,remove);return figure;
    }));
  }
  async add(files) {
    if(this.busy||this.getSending())return;
    if(!this.getAccount()?.authenticated){this.onError('Sign in before adding screenshots.');return;}
    if(!files.length)return;
    this.busy=true;this.refresh();this.onChange();
    const prepared=[];
    try {
      if(this.items.length+files.length>MAX_SCREENSHOTS)throw Error('Attach no more than 3 screenshots.');
      let total=this.items.reduce((n,item)=>n+item.file.size,0);
      for(const file of files) {
        await describeScreenshot(file);
        let bitmap,canvas;
        try {
          bitmap=await createImageBitmap(file);
          canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height;
          canvas.getContext('2d').drawImage(bitmap,0,0);
          // Re-encode pixels to remove original filenames and embedded image metadata.
          const blob=await new Promise(resolve=>canvas.toBlob(resolve,file.type,0.95));
          const metadata=await describeScreenshot(blob);
          total+=blob.size;
          if(total>MAX_SCREENSHOTS_BYTES)throw Error('Screenshots must total 10 MiB or less.');
          prepared.push({file:blob,metadata,url:URL.createObjectURL(blob)});
        } finally {bitmap?.close();if(canvas){canvas.width=0;canvas.height=0;}}
      }
      this.items.push(...prepared);
      if(!this.getSubmitted())this.consent.checked=false;
      this.onReady();
    } catch(error) {prepared.forEach(item=>URL.revokeObjectURL(item.url));this.onError(error.message);}
    finally {this.busy=false;this.refresh();this.onChange();}
  }
  metadata() {
    if(this.busy)throw Error('Wait for screenshot previews to finish.');
    return validateScreenshotMetadata(this.items.map(item=>item.metadata),this.consent.checked);
  }
  body(report) {
    const expected=report.screenshots||[],actual=this.metadata();
    if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error('Reattach the original screenshots in the same order before retrying.');
    if(!expected.length)return {headers:{'Content-Type':'application/json'},body:JSON.stringify(report)};
    const body=new FormData();body.set('report',JSON.stringify(report));
    this.items.forEach((item,i)=>body.set(`screenshot[${i}]`,item.file,screenshotName(i,item.metadata.type)));
    return {body};
  }
  clear() {this.items.forEach(item=>URL.revokeObjectURL(item.url));this.items=[];}
}
