import {readPackage,describePrivateLogs,logFilename} from './private-logs.mjs';
import {redact} from './protocol.mjs';

// One bounded, temporary browser-local bundle survives the Discord sign-in
// redirect. It never enters sessionStorage or the delivery-receipt database.
async function cache(operation,value) {
  return new Promise((resolve,reject)=>{
    let db,finished=false;
    const finish=(error,result)=>{if(finished)return;finished=true;clearTimeout(timer);db?.close();error?reject(error):resolve(result);};
    const timer=setTimeout(()=>finish(Error('Local log storage is unavailable. Reattach your saved report bundle after signing in.')),3000);
    const request=indexedDB.open('kfps-private-report-logs-v1',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('bundle');
    request.onerror=()=>finish(request.error);
    request.onblocked=()=>finish(Error('Local log storage is blocked.'));
    request.onsuccess=()=>{
      db=request.result;if(finished){db.close();return;}
      const transaction=db.transaction('bundle',operation==='get'?'readonly':'readwrite');
      const store=transaction.objectStore('bundle');
      const result=operation==='get'?store.get('current'):operation==='put'?store.put(value,'current'):store.delete('current');
      transaction.oncomplete=()=>finish(null,result.result);
      transaction.onerror=()=>finish(transaction.error);
      transaction.onabort=()=>finish(transaction.error||Error('Local log storage stopped.'));
    };
  });
}

export class PrivateLogPicker {
  constructor({onError}) {
    this.onError=onError;this.item=null;this.busy=false;this.url=null;
    this.state=document.getElementById('private-log-state');
    this.download=document.getElementById('download-private-logs');
    this.preview=document.getElementById('private-log-preview');
    addEventListener('pagehide',()=>{if(this.url)URL.revokeObjectURL(this.url);});
  }
  async accept(file,{validate=value=>value}={}) {
    this.busy=true;
    try {
      const item=await readPackage(file,{redact});
      item.report=validate(item.report);
      this.item={...item,id:item.report.id};
      try {await cache('put',{id:item.report.id,logs:item.logs,at:Date.now()});}
      catch {this.onError('Logs are ready in this tab, but could not be saved across sign-in or refresh. Reattach your saved report bundle afterwards.');}
      return item.report;
    } finally {this.busy=false;}
  }
  async restore(report) {
    this.busy=true;
    try {
      const stored=await cache('get');
      if(!stored)return;
      if(Date.now()-stored.at>24*60*60*1000||stored.at>Date.now()+60000){await cache('delete');return;}
      if(!report.private_logs)return;
      if(stored.id!==report.id)return;
      const {metadata,bundle}=await describePrivateLogs(stored.logs,{redact});
      if(JSON.stringify(metadata)!==JSON.stringify(report.private_logs))throw Error('Saved private logs do not match this report.');
      this.item={id:report.id,logs:stored.logs,metadata,bundle};
    } catch {if(report.private_logs)this.onError('Private logs could not be restored. Reattach the saved KFPS report bundle before sending.');}
    finally {this.busy=false;}
  }
  refresh(report,included=true) {
    const wanted=report.private_logs;
    if(this.url){URL.revokeObjectURL(this.url);this.url=null;}
    this.download.hidden=true;this.preview.textContent='';
    if(!included){this.state.textContent='Private logs will not be sent because technical details are turned off.';return;}
    if(!wanted){this.state.textContent='No complete application logs attached. Older reports may contain excerpts only.';return;}
    if(!this.item||this.item.id!==report.id||this.item.metadata.sha256!==wanted.sha256) {
      this.state.textContent='Private logs are missing. Add the saved report.kfps-report.json.gz bundle below before sending.';return;
    }
    this.state.textContent=`${wanted.files} retained log file(s), ${(wanted.size/1024).toFixed(1)} KB compressed. Private to Kloudy and authorized support staff.${wanted.warnings.length?' Some records could not be included: '+wanted.warnings.join(' '):' No retained files or valid records were omitted.'}`;
    this.url=URL.createObjectURL(this.item.logs);this.download.href=this.url;this.download.download=logFilename(report.id,wanted.schema);this.download.hidden=false;
    this.preview.textContent=this.item.bundle.files.map(file=>`${file.name} (${file.source_bytes} original bytes; ${file.omitted_lines} omitted lines)\n${file.text.slice(-1600)}`).join('\n\n');
  }
  attach(report,upload) {
    if(!report.private_logs)return upload;
    if(!this.item||this.item.id!==report.id||JSON.stringify(this.item.metadata)!==JSON.stringify(report.private_logs))throw Error('Reattach the original saved KFPS report bundle. The complete private logs are missing.');
    const body=upload.body instanceof FormData?upload.body:new FormData();
    body.set('report',JSON.stringify(report));body.set('private_logs',this.item.logs,logFilename(report.id,report.private_logs.schema));
    return {body};
  }
  async clear() {
    this.item=null;if(this.url)URL.revokeObjectURL(this.url);this.url=null;
    try {await cache('delete');} catch {this.onError('Local log cleanup failed. Clear this site\'s data to remove its temporary private-log copy.');}
  }
}
