import {readPackage,describePrivateLogs,logFilename} from './private-logs.mjs';
import {redact} from './protocol.mjs';
import {reportText} from './report-copy.mjs';
import {t,logWarning} from './report-locale.mjs';

// One current bundle and one bounded replacement journal. The journal bridges
// the non-atomic draft-storage/IndexedDB boundary without discarding the old log.
async function cache(operation,value,key='current') {
  return new Promise((resolve,reject)=>{
    let db,transaction,finished=false;
    const finish=(error,result)=>{if(finished)return;finished=true;clearTimeout(timer);if(error)try{transaction?.abort();}catch{}db?.close();error?reject(error):resolve(result);};
    const timer=setTimeout(()=>finish(Error('Local log storage is unavailable. Reattach your saved report bundle after signing in.')),3000);
    let request;
    try {request=indexedDB.open('kfps-private-report-logs-v1',1);}catch(error){finish(error);return;}
    request.onupgradeneeded=()=>request.result.createObjectStore('bundle');
    request.onerror=()=>finish(request.error);
    request.onblocked=()=>finish(Error('Local log storage is blocked.'));
    request.onsuccess=()=>{
      db=request.result;if(finished){db.close();return;}
      try {
        transaction=db.transaction('bundle',operation==='get'?'readonly':'readwrite');
        const store=transaction.objectStore('bundle');
        let result;
        transaction.oncomplete=()=>finish(null,result?.result);
        transaction.onerror=()=>finish(transaction.error);
        transaction.onabort=()=>finish(transaction.error||Error('Local log storage stopped.'));
        if(operation==='get')result=store.get(key);
        else if(operation==='put')store.put(value,'current');
        else if(operation==='promote'){store.put(value,'current');store.delete('pending');}
        else {
          const slot=operation==='stage'||operation==='discard'?'pending':'current';
          const found=store.get(slot);
          found.onsuccess=()=>{try {
            if(operation==='stage') {
              if(found.result&&found.result.id!==value.id&&Date.now()-found.result.at<60000)throw Error('Another report replacement is still being saved. Try again shortly.');
              store.put(value,'pending');
            } else if(found.result?.id===value?.id)store.delete(slot);
          }catch(error){finish(error);}};
        }
      }catch(error){finish(error);}
    };
  });
}

export class PrivateLogPicker {
  constructor({onError}) {
    this.onError=onError;this.item=null;this.busy=false;this.url=null;this.storageWarning=false;
    this.state=document.getElementById('private-log-state');
    this.download=document.getElementById('download-private-logs');
    this.preview=document.getElementById('private-log-preview');
    addEventListener('pagehide',()=>{if(this.url)URL.revokeObjectURL(this.url);});
  }
  async prepare(file,{validate=value=>value}={}) {
    this.busy=true;
    try {
      const item=await readPackage(file,{redact});
      item.report=validate(item.report);
      return {...item,id:item.report.id};
    } finally {this.busy=false;}
  }
  async stage(item) {
    const pending=await cache('get',null,'pending');
    // A previous interrupted promotion may be the only durable copy of the
    // active report's archive. Finish it before reusing the journal slot.
    if(pending&&pending.id===this.item?.id)await cache('promote',pending);
    await cache('stage',{id:item.id,logs:item.logs,at:Date.now()});
  }
  async discard(item) {
    try {await cache('discard',{id:item.id});}catch{this.onError(reportText('cacheWarning'));}
  }
  async commit(item,{staged=false,persist=true}={}) {
    this.busy=true;
    try {
      this.item=item;
      this.storageWarning=!persist;
      if(persist)try {await cache(staged?'promote':'put',{id:item.id,logs:item.logs,at:Date.now()});}
      catch {this.storageWarning=true;this.onError(reportText('cacheWarning'));}
    } finally {this.busy=false;}
  }
  async restore(report) {
    this.busy=true;
    try {
      let stored=await cache('get');
      const pending=await cache('get',null,'pending');
      if(pending?.id===report.id&&report.private_logs){stored=pending;}
      else if(pending&&Date.now()-pending.at>24*60*60*1000)await cache('discard',pending);
      if(!stored)return;
      if(Date.now()-stored.at>24*60*60*1000||stored.at>Date.now()+60000){await cache(stored===pending?'discard':'delete',stored);return;}
      if(!report.private_logs)return;
      if(stored.id!==report.id)return;
      const {metadata,bundle}=await describePrivateLogs(stored.logs,{redact});
      if(JSON.stringify(metadata)!==JSON.stringify(report.private_logs))throw Error('Saved private logs do not match this report.');
      this.item={id:report.id,logs:stored.logs,metadata,bundle};
      if(stored===pending)try{await cache('promote',stored);}catch{this.storageWarning=true;this.onError(reportText('cacheWarning'));}
    } catch {if(report.private_logs)this.onError(reportText('restoreWarning'));}
    finally {this.busy=false;}
  }
  refresh(report,included=true) {
    const wanted=report.private_logs;
    if(this.url){URL.revokeObjectURL(this.url);this.url=null;}
    this.download.hidden=true;this.preview.textContent='';
    if(!included){this.state.textContent=reportText('excludedLogs');return;}
    if(!wanted){this.state.textContent=reportText('noLogs');return;}
    if(!this.ready(report)) {
      this.state.textContent=reportText(window.KFPSNativeReport===true?'nativeMissing':'browserMissing');return;
    }
    this.state.textContent=`${wanted.files} ${reportText('readyLogs')}; ${(wanted.size/1024).toFixed(1)} KB ${reportText('compressed')} ${wanted.warnings.length?reportText('omittedLogs')+wanted.warnings.map(logWarning).join(' '):reportText('noOmissions')}`;
    this.url=URL.createObjectURL(this.item.logs);this.download.href=this.url;this.download.download=logFilename(report.id,wanted.schema);this.download.hidden=false;
    this.preview.textContent=this.item.bundle.files.map(file=>t('{0} ({1} original bytes; {2} omitted lines)',file.name,file.source_bytes,file.omitted_lines)+`\n${file.text.slice(-1600)}`).join('\n\n');
  }
  ready(report) {
    return !this.busy&&!!report.private_logs&&report.private_logs.files>0&&this.item?.id===report.id
      &&this.item.logs?.size===report.private_logs.size&&JSON.stringify(this.item.metadata)===JSON.stringify(report.private_logs);
  }
  attach(report,upload) {
    if(report.include_technical===false)return upload;
    if(!this.ready(report))throw Error(reportText('noLogs'));
    const body=upload.body instanceof FormData?upload.body:new FormData();
    body.set('report',JSON.stringify(report));body.set('private_logs',this.item.logs,logFilename(report.id,report.private_logs.schema));
    return {body};
  }
  async clear() {
    const id=this.item?.id;
    this.item=null;if(this.url)URL.revokeObjectURL(this.url);this.url=null;
    this.storageWarning=false;
    try {if(id){await cache('delete',{id});await cache('discard',{id});}} catch {this.onError('Local log cleanup failed. Clear this site\'s data to remove its temporary private-log copy.');}
  }
}
