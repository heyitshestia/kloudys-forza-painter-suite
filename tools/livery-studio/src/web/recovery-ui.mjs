/** Disk recovery is separate from file save. Call changed() on committed edits,
 * undo/redo, and changed({newDocument:true}) on explicit new/open, never on drag
 * preview. getProject must return committed data; isBusy includes numeric drafts
 * and gestures, but excludes this module's modal. loadProject(project,{isCurrent})
 * must use the existing atomic loader and check isCurrent immediately before swap.
 * No recovery is loaded automatically. config is the current editor config.
 */
import { serializeProject } from './layout-model.mjs';
import {t,localizeStatic,errorText as localizeError,date} from './i18n.mjs';

const identifier = value => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value);
const newId = () => crypto.randomUUID().replaceAll('-', '');
const errorText = error => localizeError(error?.message || 'Recovery could not be completed.');
const shortName = name => typeof name === 'string' && name.trim() && name.length <= 80 && !/[\x00-\x1f\x7f]/.test(name);

// Exported for focused transaction/lifecycle tests. The DOM wrapper below uses
// the same controller; it is not a second implementation of recovery behavior.
export function createRecoveryController({api,getProject,loadProject,isBusy=()=>false,onState=()=>{},debounceMs=1500}) {
  let documentId=newId(),revision=0,generation=0,pending=false,phase='',disposed=false,timer=null,lastError='',entries=[];
  const delay=Math.max(100,Math.min(10000,debounceMs));
  const state=()=>({documentId,pending,phase,disposed,error:lastError,entries:[...entries]});
  const notify=()=>{if(!disposed)onState(state());};
  const clear=()=>{if(timer!==null)clearTimeout(timer);timer=null;};
  const alive=(g,r)=>!disposed&&generation===g&&(r===undefined||revision===r);
  const capture=()=>JSON.parse(serializeProject(getProject()));
  const schedule=()=>{clear();if(!disposed&&pending&&!phase)timer=setTimeout(()=>{timer=null;void automatic();},delay);};
  function changed({newDocument=false}={}) {
    if(disposed)return;
    if(newDocument){generation++;documentId=newId();}
    revision++;pending=true;lastError='';schedule();notify();
  }
  async function automatic() {
    if(disposed||!pending||phase)return;
    if(isBusy()){schedule();return;}
    const g=generation,r=revision,id=documentId;
    phase='saving';notify();
    let succeeded=false;
    try {
      const value=await api('recovery',{document_id:id,kind:'auto',project:capture()});
      if(!identifier(value?.entry?.id))throw Error('Invalid recovery save response.');
      succeeded=true;
      if(alive(g,r)){pending=false;lastError='';}
    } catch(error) {if(alive(g))lastError=errorText(error);}
    finally {
      phase='';
      // Do not spin on a full/corrupt store. New edits or an explicit retry can
      // retry; changes made while an older save was in flight are never lost.
      if(!disposed&&pending&&(succeeded||!alive(g,r)))schedule();
      notify();
    }
  }
  async function list() {
    const g=generation;
    const value=await api('recovery');
    if(value?.version!==1||!Array.isArray(value.entries)||value.entries.length>128
      ||value.entries.some(e=>!identifier(e?.id)||!identifier(e?.document_id)||!['auto','checkpoint','before-restore'].includes(e.kind)
        ||typeof e.name!=='string'||e.name.length>80||typeof e.created_at!=='string'))throw Error('Invalid recovery list response.');
    if(alive(g)){entries=value.entries;notify();}
    return value.entries;
  }
  function requireIdle() {
    if(disposed||phase||isBusy())throw Error('Finish or cancel the current edit before using recovery.');
  }
  async function checkpoint(name) {
    requireIdle();
    if(!shortName(name))throw Error('Give the checkpoint a name of 1-80 characters.');
    const g=generation,r=revision;
    clear();phase='checkpoint';lastError='';notify();
    try {
      const result=await api('recovery',{document_id:documentId,kind:'checkpoint',name:name.trim(),project:capture()});
      if(!identifier(result?.entry?.id))throw Error('Invalid checkpoint response.');
      if(alive(g,r))pending=false;
      return result.entry;
    } catch(error) {if(alive(g))lastError=errorText(error);throw error;}
    finally {phase='';if(pending)schedule();notify();}
  }
  async function restore(entryId) {
    requireIdle();
    if(!identifier(entryId))throw Error('Choose a recovery entry.');
    const g=generation,r=revision,current=capture(),before=JSON.stringify(current);
    clear();phase='restoring';lastError='';notify();
    try {
      const result=await api(`recovery/${entryId}/restore`,{document_id:documentId,current_project:current});
      if(!identifier(result?.entry?.document_id)||!identifier(result?.retained?.id)||!result.project)throw Error('Invalid recovery response. The current layout was not replaced.');
      const isCurrent=()=>alive(g,r)&&JSON.stringify(capture())===before;
      if(isBusy()||!isCurrent())throw Error('The layout changed while recovery was preparing. Nothing was replaced; choose the entry again.');
      // The loader is responsible for atomic resource preparation. The guard
      // also prevents a late response from replacing a different/new document.
      const loaded=await loadProject(result.project,{isCurrent});
      if(loaded===false)throw Error('Recovery loading was cancelled. The current layout was not replaced.');
      if(!alive(g,r))throw Error('Recovery was interrupted. The pre-restore layout remains in recovery.');
      documentId=result.entry.document_id;generation++;revision++;pending=false;
      return result;
    } catch(error) {if(alive(g))lastError=errorText(error);throw error;}
    finally {phase='';if(pending)schedule();notify();}
  }
  function unloadPayload() {
    if(disposed||!pending||phase||isBusy())return null;
    try {
      const body=JSON.stringify({document_id:documentId,kind:'auto',project:capture()});
      // Chromium's shared keepalive budget is 64 KiB. Larger layouts depend on
      // the normal debounced save; never claim that unload is a guaranteed save.
      return new TextEncoder().encode(body).byteLength<=60*1024?body:null;
    } catch {return null;}
  }
  return {changed,list,checkpoint,restore,automatic,unloadPayload,state,
    refresh(){if(pending&&!phase&&timer===null&&!lastError)schedule();notify();},
    dispose(){disposed=true;generation++;clear();}};
}

export function initRecovery({host,api,getProject,loadProject,message=()=>{},isBusy=()=>false,config={}}) {
  if(!host)throw Error('Recovery needs a toolbar host.');
  const doc=host.ownerDocument||document,win=doc.defaultView||window;
  const make=(tag,text,attrs={})=>{const el=doc.createElement(tag);if(text)el.textContent=text;for(const [key,value] of Object.entries(attrs))el.setAttribute(key,value);return el;};
  const unique=newId(),open=make('button','Recovery',{type:'button','data-recovery':'open',title:'Automatic recovery and named checkpoints for this car'});
  const dialog=make('dialog','',{'aria-labelledby':`recovery-title-${unique}`,'data-recovery':'dialog'});
  const heading=make('h2','Recovery & checkpoints',{id:`recovery-title-${unique}`});
  const status=make('p','',{class:'experiment-status','aria-live':'polite','data-recovery':'status'});
  const field=make('label','Checkpoint name',{class:'field'});
  const name=make('input','',{type:'text',maxlength:'80',placeholder:'e.g. Blue variant','data-recovery':'name'});field.append(name);
  Object.assign(name.style,{minWidth:'0',width:'100%',padding:'6px',background:'var(--field)',color:'var(--text)',border:'1px solid var(--line)',borderRadius:'3px'});
  dialog.style.width='560px';
  const save=make('button','Save checkpoint',{type:'button','data-recovery':'checkpoint'});
  const listLabel=make('label','Saved recovery for this car',{class:'field'});
  const select=make('select','',{'aria-label':'Saved recovery for this car','data-recovery':'entries'});listLabel.append(select);
  const description=make('p','',{class:'experiment-status','data-recovery':'description'});
  const actions=make('div','',{class:'actions'}),reload=make('button','Refresh',{type:'button','data-recovery':'reload'}),restore=make('button','Restore selected',{type:'button','data-recovery':'restore'});
  const confirm=make('div','',{'data-recovery':'confirm'});confirm.hidden=true;
  const warning=make('p','Replace the open layout with this entry? Your current layout will be kept as a separate "Before restore" copy.',{class:'experiment-status'});
  const confirmationActions=make('div','',{class:'actions'}),yes=make('button','Keep current & restore',{type:'button','data-recovery':'confirm-restore'}),no=make('button','Cancel',{type:'button','data-recovery':'cancel-restore'});
  const bottom=make('div','',{class:'actions'}),close=make('button','Close',{type:'button','data-recovery':'close'});
  confirmationActions.append(no,yes);confirm.append(warning,confirmationActions);actions.append(reload,restore);bottom.append(close);
  dialog.append(heading,field,save,listLabel,description,actions,confirm,status,bottom);localizeStatic(dialog);localizeStatic(open);host.append(open);doc.body.append(dialog);
  let disposed=false,loading=false,lastList='',reportedError='',lastPhase='',unloadBody='',controller;
  function feedback(text,error=false){text=t(text);status.textContent=text;status.classList.toggle('error',error);message(text,error);}
  function render(state) {
    const blocked=loading||!!state.phase||isBusy();
    // Reading the recovery list is safe during an automatic write. Do not make
    // a background debounce disable this button halfway through a user click.
    open.disabled=loading||isBusy()||state.phase==='checkpoint'||state.phase==='restoring';
    save.disabled=blocked;reload.disabled=blocked;select.disabled=blocked;name.disabled=blocked;
    restore.disabled=blocked||!state.entries.length;yes.disabled=blocked||!state.entries.length;
    no.disabled=!!state.phase;close.disabled=!!state.phase;
    const signature=JSON.stringify(state.entries);
    if(signature!==lastList) {
      lastList=signature;const previous=select.value;
      select.replaceChildren(...state.entries.map(entry=>make('option',`${entry.kind==='auto'?t('Automatic snapshot'):entry.kind==='before-restore'?t('Before restore'):entry.name} / ${date(entry.created_at)}`,{value:entry.id})));
      if(state.entries.some(entry=>entry.id===previous))select.value=previous;
      if(!state.entries.length)select.append(make('option',t('No recovery entries yet'),{value:''}));
    }
    open.textContent=state.error?t('Recovery unavailable'):state.entries.length?t`Recovery (${state.entries.length})`:t('Recovery');
    const entry=state.entries.find(entry=>entry.id===select.value);
    description.textContent=entry?t`${t(entry.kind==='checkpoint'?'Named checkpoint':entry.kind==='before-restore'?'Retained before restore':'Automatic snapshot')} / ${entry.sources} sources / ${entry.placements} placements`:t('No recovery entries for this car.');
    if(state.error){status.textContent=state.error;status.classList.add('error');if(reportedError!==state.error){reportedError=state.error;message(state.error,true);}}
    else if(state.phase){status.textContent=t(state.phase==='restoring'?'Retaining current layout and loading recovery...':'Saving recovery...');status.classList.remove('error');}
    else if(lastPhase||reportedError){status.textContent=lastPhase==='saving'?t('Automatic recovery saved.'):'';status.classList.remove('error');}
    else if(!dialog.open)status.textContent='';
    lastPhase=state.phase;
    if(!state.error)reportedError='';
    if(state.error){open.title=state.error;open.setAttribute('aria-label',t`Recovery: ${state.error}`);}
    else {open.title=t('Automatic recovery and named checkpoints for this car');open.removeAttribute('aria-label');}
  }
  controller=createRecoveryController({api,getProject,loadProject,isBusy,onState:render,debounceMs:config.recovery?.debounce_ms??1500});
  async function loadList(){loading=true;render(controller.state());try{await controller.list();}catch(error){if(!disposed)feedback(errorText(error),true);}finally{loading=false;if(!disposed)render(controller.state());}}
  open.addEventListener('click',()=>{if(open.disabled||disposed)return;confirm.hidden=true;status.textContent='';dialog.showModal();void loadList();});
  close.addEventListener('click',()=>{if(!close.disabled)dialog.close();});
  dialog.addEventListener('cancel',event=>{if(controller.state().phase)event.preventDefault();});
  // Native input editing, IME and AltGr must not reach editor shortcuts.
  dialog.addEventListener('keydown',event=>{
    event.stopPropagation();
    if(!event.isComposing&&event.keyCode!==229&&!event.altKey&&!event.getModifierState?.('AltGraph')
      &&(event.ctrlKey||event.metaKey)&&event.code==='KeyS')event.preventDefault();
  });
  // Disabling the focused field during a request can move focus to body even
  // while a modal is open. Keep that transient target out of editor shortcuts.
  const modalKeys=event=>{
    if(!dialog.open||(event.target?.nodeType&&dialog.contains(event.target)))return;
    event.stopImmediatePropagation();
    if(!event.isComposing&&event.keyCode!==229&&!event.altKey&&!event.getModifierState?.('AltGraph')
      &&(event.ctrlKey||event.metaKey)&&['KeyS','KeyZ','KeyY','KeyD'].includes(event.code))event.preventDefault();
  };
  win.addEventListener('keydown',modalKeys,{capture:true});
  select.addEventListener('change',()=>{confirm.hidden=true;render(controller.state());});
  reload.addEventListener('click',()=>void loadList());
  save.addEventListener('click',async()=>{
    try{const entry=await controller.checkpoint(name.value);if(disposed)return;feedback('Checkpoint saved. Your layout file has not been marked saved.');await loadList();if(!disposed){select.value=entry.id;render(controller.state());}}
    catch(error){if(!disposed)feedback(errorText(error),true);}
  });
  restore.addEventListener('click',()=>{if(!restore.disabled){confirm.hidden=false;yes.focus();}});
  no.addEventListener('click',()=>{confirm.hidden=true;restore.focus();});
  yes.addEventListener('click',async()=>{
    try{await controller.restore(select.value);if(disposed)return;confirm.hidden=true;feedback('Recovery loaded. The previous layout is retained separately. Save the layout file when ready.');await loadList();}
    catch(error){if(!disposed)feedback(errorText(error),true);}
  });
  const pagehide=()=>{
    const body=controller.unloadPayload();
    if(body&&body!==unloadBody){unloadBody=body;try{void win.fetch(new URL('./api/recovery',win.location.href),{method:'POST',headers:{'Content-Type':'application/json'},body,keepalive:true}).catch(()=>{});}catch{}}
  };
  // Native event dispatch can run an earlier listener's queued microtask before
  // this listener. dispose also flushes before removing our pending state.
  win.addEventListener('pagehide',pagehide,{capture:true});
  void loadList();
  return {changed:options=>controller.changed(options),refresh:()=>controller.refresh(),dispose(){if(disposed)return;pagehide();disposed=true;controller.dispose();win.removeEventListener('pagehide',pagehide,{capture:true});win.removeEventListener('keydown',modalKeys,{capture:true});dialog.remove();open.remove();}};
}
