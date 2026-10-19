import { studioDiagnostics as diagnostics, projectCounts } from './diagnostics.mjs';
import { sceneReady, updatePaintCanvas, sceneState, sceneDiagnosticMetrics, isSceneReady, currentVehicleParts, validatePartConfiguration, setVehicleParts } from './livery-scene.js';
import { createSurfaceEditor } from './surface-edit.mjs';
import { initializeStudioTools } from './studio-tools.mjs';
import * as authoring from './authoring-model.mjs';
import * as mirror from './mirror-links.mjs';
import { initRecovery } from './recovery-ui.mjs';
import { initProjectStorage } from './project-storage-ui.mjs';
import { initInspection } from './inspection-tools.mjs';
import { initializeActionConfirmations } from './action-confirmations.mjs';
import { confirmationSpec } from './confirmation-policy.mjs';
import {t,sectionLabel,number,stateLabel,errorText} from './i18n.mjs';
import { emptyProject, validateProject, serializeProject, sectionVinylJson, sectionShapeCount, placementMatrix, invertMatrix, mapPoint, sectionToPaint, createHistory, makePlacement, scalePlacement, movePlacementToSection, placementStepIndex, transformPlacement, MAX_VINYLS, MAX_PLACEMENTS, MAX_NATIVE_VINYL_SHAPES } from './layout-model.mjs';

const $ = id => document.getElementById(id), stop = new AbortController();
const sectionCanvas = $('sectionCanvas'), sectionContext = sectionCanvas.getContext('2d');
const atlas = document.createElement('canvas'), atlasContext = atlas.getContext('2d');
const images = new Map(), sources = new Map(), sectionCanvases = new Map(), history = createHistory(100,MAX_VINYLS*2);
let config, project, selected = null, pickedSource = null, saved = '', busy = false, disposed = false, queued = 0, drag = null;
let experimentNotice = '', experimentError = false;
let transform = null, surface = null, surfaceMode = 'orbit', sourceSignature = '', placementSignature = '';
const sourceButtons = new Map(), placementButtons = new Map();
const modes = {orbit:'Orbit',move:'Move',scale:'Scale',rotate:'Rotate',skew:'Skew'};
const dirtySections = new Set();
const metrics = { paintUpdates: 0, lastComposeMs: 0, maxComposeMs: 0 };
diagnostics.setSampler(()=>({...sceneDiagnosticMetrics(),...projectCounts(project,config?.sections?.length||0),compose_ms:metrics.lastComposeMs}));
const numeric = { positionX: 'x', positionY: 'y', scaleX: 'scaleX', scaleY: 'scaleY', rotation: 'rotation', skew:'skew', opacity: 'opacity' };
const numericDisplay = new Map(), numericEdited = new Set();
let sliderPointer = null;
const completedHandoffs = new Set();
const nativeDownloads = new Map();
let handoffWorking=false;
let externalPicker=null;
let previewError='';
let saveWorking=false;
let selectedIds=[],tools=null,recovery=null,inspection=null,sourceEdit=null,confirmations=null,projectStorage=null;
let sourceDocumentId=crypto.randomUUID();
let snapGuide=null;
let carCatalogue=[],carCurrent=null,carPicked=null,carJob=null,carWorking=false,carCommitting=false,carCancelRequested=false,navigationAuthorized=false;
function interactionBusy() { return busy || saveWorking || !!drag || !!transform || externalPicker!==null || projectStorage?.isOpen()===true; }
function canPreview() { return !previewError&&isSceneReady(); }
function editBlocked() { return interactionBusy()||!canPreview(); }
function requirePreview() { if(!canPreview())throw Error('The preview is unavailable. Save the current layout, then reload the preview.'); }
const componentExportReason = 'Configured body/parts are saved in the layout, but experimental game export cannot yet encode/verify them. Restore stock preview to export artwork against template.';
function nonstockPreview() { return Object.keys(project?.vehicle_parts||{}).length>0||Object.keys(currentVehicleParts()).length>0; }
function retainParts(value) { if(Object.keys(value||{}).length)project.vehicle_parts=structuredClone(value);else delete project.vehicle_parts; }
function message(text, error = false) { if(error)diagnostics.emit('error',{error_code:'operation'}); $('notice').textContent = error?errorText(text):t(text); $('notice').classList.toggle('error', error); }
function experimentMessage(text, error = false) {
  text=error?errorText(text):t(text);experimentNotice=text;experimentError=error;
  $('experimentStatus').textContent=text;$('experimentStatus').classList.toggle('error',error);
  if(error)$('exportDetails').open=true;
}
function snapshot() { return { vinylIds: project.vinyls.map(v => v.id), placements: structuredClone(project.placements), selected,selectedIds:[...selectedIds],authoring:structuredClone(project.authoring||null), vehicle_parts:structuredClone(project.vehicle_parts||{}) }; }
function current() { return project.placements.find(p => p.id === selected); }
function locked(id) { return project.authoring?.locked?.includes(id)===true; }
function normaliseSelection() {
  selectedIds=selectedIds.filter(id=>project.placements.some(p=>p.id===id));
  if(selected&&!selectedIds.includes(selected))selectedIds=[selected];
  if(!selected)selectedIds=[];
}
function artworkBounds(vinylId) {
  if(disposed)return null;
  const image=images.get(vinylId),bounds=image?.artworkBounds;
  if(!Array.isArray(bounds)||bounds.length!==4||!bounds.every(Number.isFinite))return null;
  const [left,top,right,bottom]=bounds;
  if(left<0||top<0||right>image.width||bottom>image.height||right<=left||bottom<=top)return null;
  return [...bounds];
}
function getBounds(id) { return artworkBounds(project?.placements.find(item=>item.id===id)?.vinylId); }
function selectPlacement(id,section,options={}) {
  if(interactionBusy()||disposed||!flushNumeric())return false;
  const placement=project.placements.find(p=>p.id===id);
  if(id!==null&&!placement)return false;
  if(section!==undefined&&!config.sections.some(item=>item.section===section))return false;
  const group=!options.individual&&project.authoring?.groups?.find(group=>group.placements.includes(id));
  const ids=group?[...group.placements]:placement?[id]:[];
  if(options.additive){
    selectedIds=ids.every(value=>selectedIds.includes(value))?selectedIds.filter(value=>!ids.includes(value)):[...new Set([...selectedIds,...ids])];
    selected=selectedIds.includes(id)?id:selectedIds.at(-1)||null;
  }else if(!id||!selectedIds.includes(id)||options.individual||(group&&!ids.every(value=>selectedIds.includes(value)))){selectedIds=ids;selected=placement?.id||null;}
  else selected=id;
  if(placement){pickedSource=placement.vinylId;$('section').value=placement.section;}
  else if(section)$('section').value=section;
  refresh();schedule();return true;
}
function refreshTransformFields() {
  const placement=current();
  for(const [id,key] of Object.entries(numeric)) {
    if(!previewError&&numericEdited.has(id)&&numericDisplay.get(id)?.placementId===placement?.id)continue;
    const value=placement?(placement[key]??0):'';
    const text=placement?String(Number(value.toFixed(6))):'';
    $(id).value=text;$(id).setAttribute('aria-invalid','false');numericDisplay.set(id,{placementId:placement?.id,text});numericEdited.delete(id);
    $(id+'Range').value=placement?value:$(id+'Range').min;
  }
}
function commitNumeric(id) {
  if(editBlocked()||disposed||!current())return false;
  const field=$(id),display=numericDisplay.get(id);
  if(display?.placementId!==selected||field.value!==display.text)numericEdited.add(id);
  if(!numericEdited.size)return true;
  let invalidField=field,next=current();
  try {
    // Validate every pending draft before refresh can replace any field text.
    for(const pending of numericEdited) {
      const input=$(pending),key=numeric[pending];invalidField=input;
      if(!input.checkValidity()||input.value===''||!Number.isFinite(input.valueAsNumber))throw Error(t`${t({x:'X',y:'Y',scaleX:'Scale X',scaleY:'Scale Y',rotation:'Rotation (deg)',skew:'Skew',opacity:'Opacity'}[key])}: Enter a number between ${input.min} and ${input.max}.`);
      next=key==='scaleX'||key==='scaleY'?scalePlacement(next,key,input.valueAsNumber,$('aspectLock').checked):transformPlacement(next,{[key]:input.valueAsNumber});
    }
    numericEdited.clear();
    const patch=Object.fromEntries(Object.keys(numeric).map(id=>numeric[id]).filter(key=>next[key]!==current()[key]).map(key=>[key,next[key]??0]));
    edit(()=>{project=transformProject(project,selected,patch,{bypassSnap:true});});message('Placement updated.');return true;
  } catch(error) {
    invalidField.setAttribute('aria-invalid','true');message(t`${errorText(error)} The placement was not changed.`,true);return false;
  }
}
function flushNumeric() {
  const pending=numericEdited.values().next().value;
  return !pending||commitNumeric(pending);
}
function cancelNumeric(id) {
  const display=numericDisplay.get(id);
  if(display?.placementId!==selected)return;
  $(id).value=display.text;$(id).setAttribute('aria-invalid','false');numericEdited.delete(id);
  $('documentState').textContent=t(changed()?'Unsaved layout':'Saved layout');
  message('Numeric edit cancelled.');
}
function refreshSectionCount() {
  const count=sectionShapeCount(project,$('section').value),node=$('sectionShapeCount');
  node.textContent=t`${number(count)} source shapes / ${number(MAX_NATIVE_VINYL_SHAPES)} vinyl export limit`;
  node.classList.toggle('over-limit',count>MAX_NATIVE_VINYL_SHAPES);
  const cap=config.livery_section_policy?.section_caps?.[$('section').value],notice=$('liverySectionCap');
  const known=Number.isSafeInteger(cap)&&cap>0;
  notice.textContent=known?t`Livery cap: ${number(cap)} shapes (FLS fallback)`:t('Livery cap unavailable.');
  notice.classList.toggle('error',known&&count>cap);
}
function beginTransform(id,kind='surface',field=null) {
  if(editBlocked()||disposed||!flushNumeric())return false;
  const placement=project.placements.find(p=>p.id===id);
  if(!placement||locked(id)||selectedIds.some(locked)){message('Unlock the selected placements before editing.',true);return false;}
  selected=id;pickedSource=placement.vinylId;$('section').value=placement.section;
  transform={id,kind,field,before:snapshot()};refresh();return true;
}
function previewTransform(id,patch,options={}) {
  if(!transform||transform.id!==id||busy||disposed||!canPreview())return false;
  const index=project.placements.findIndex(p=>p.id===id);
  if(index<0)return false;
  try {
    const base=projectAt(transform.before);
    project=transformProject(base,id,patch,options);config.sections.forEach(s=>dirtySections.add(s.section));schedule();refreshTransformFields();
    if(Object.hasOwn(patch,'opacity'))refreshSectionCount();
    $('documentState').textContent=t('Transform preview');
    return true;
  } catch(error){message(error.message,true);return false;}
}
function projectAt(state) { const value={...project,placements:state.placements};if(state.authoring)value.authoring=state.authoring;else delete value.authoring;return value; }
function transformProject(base,id,patch,{bypassSnap=false}={}) {
  const ids=selectedIds.includes(id)?selectedIds:[id],original=base.placements.find(p=>p.id===id);
  snapGuide=null;
  if(ids.some(value=>base.authoring?.locked?.includes(value)))throw Error('Unlock the selected placements before editing.');
  if(tools?.snapping()&&!bypassSnap&&(Object.hasOwn(patch,'x')||Object.hasOwn(patch,'y'))){
    const snap=authoring.snapTranslation(base,ids,{dx:(patch.x??original.x)-original.x,dy:(patch.y??original.y)-original.y,tolerance:6},getBounds);
    patch={...patch,x:original.x+snap.dx,y:original.y+snap.dy};
    snapGuide=snap;
    tools.status('snapStatus',snap.snappedX||snap.snappedY?'Aligned to guide':'');
  }
  const next=authoring.transformSelection(base,ids,id,patch,getBounds);
  return base.authoring?.links?.length?mirror.propagateLinks(base,next,ids).project:next;
}
function syncSourceLinks(before,next) {
  for(const link of next.authoring?.links||[]){
    const endpoints=[link.a,link.b],changed=endpoints.filter(id=>before.placements.find(p=>p.id===id)?.vinylId!==next.placements.find(p=>p.id===id)?.vinylId);
    if(changed.length!==1)continue;
    const edited=next.placements.find(p=>p.id===changed[0]),peer=next.placements.find(p=>p.id===endpoints.find(id=>id!==edited.id));
    if(locked(peer.id))throw Error('Unlock both linked sides before changing artwork.');
    const source=next.vinyls.find(v=>v.id===edited.vinylId),copy={id:crypto.randomUUID(),name:source.name,shapes:link.mode==='mirror-artwork'?mirror.reflectArtwork(source.shapes):structuredClone(source.shapes)};
    next={...next,placements:next.placements.map(p=>p.id===peer.id?{...p,vinylId:copy.id}:p),vinyls:[...next.vinyls,copy]};
    const used=new Set(next.placements.map(p=>p.vinylId));next.vinyls=next.vinyls.filter(v=>used.has(v.id));
  }
  return next;
}
async function applyProjectChange(next,label,ids=selectedIds) {
  const checked=validateProject(next,config.vehicle,config.sections.map(s=>s.section));serializeProject(checked);
  const before=snapshot(),newImages=new Map();
  try{
    for(const vinyl of checked.vinyls){
      const existing=sources.get(vinyl.id);
      if(existing&&JSON.stringify(existing.shapes)!==JSON.stringify(vinyl.shapes))throw Error('A source revision must have a new identity.');
      if(!images.has(vinyl.id))newImages.set(vinyl.id,await raster(vinyl.shapes));
    }
    if(disposed)throw Error('The editor is closed.');
    project=checked;for(const vinyl of checked.vinyls)sources.set(vinyl.id,vinyl);
    for(const [id,image] of newImages)images.set(id,image);
    selectedIds=ids.filter(id=>project.placements.some(p=>p.id===id));selected=selectedIds.includes(selected)?selected:selectedIds.at(-1)||null;
    markAll();commit(before);message(label);
  }catch(error){for(const image of newImages.values())image.src='';throw error;}
}
async function confirmOperation(spec) {
  if(!spec||!confirmations)return false;
  const before=fingerprint(),documentId=sourceDocumentId,ids=JSON.stringify(selectedIds);
  setBusy(true);
  try{
    const accepted=await confirmations.confirm(spec);
    if(!accepted||disposed){diagnostics.emit('action',{action:'cancel',outcome:'cancelled'});return false;}
    if(before!==fingerprint()||documentId!==sourceDocumentId||ids!==JSON.stringify(selectedIds)){
      message('The selection or document changed. Please review and try the action again.',true);return false;
    }
    return true;
  }finally{if(!disposed)setBusy(false);}
}
function sourceEditMessage(text,job=sourceEdit){
  const count=job?.customizationWarnings;
  const warning=Number.isSafeInteger(count)&&count>0?t`${count} unused custom themes could not be inherited. Your selected theme and other settings were preserved.`:'';
  tools.status('sourceEditStatus',[t(text),warning].filter(Boolean).join(' '));
}
async function studioAction(action,...args) {
  if(editBlocked()||disposed||!flushNumeric())return;
  const diagnosticAction={resetConfirmations:'reset',clearSelection:'selection',selectSection:'selection',editSource:'source_edit',cancelSourceEdit:'cancel',applySourceEdit:'source_return'}[action]||'edit';
  diagnostics.emit('action',{action:diagnosticAction,outcome:'requested'});
  if(action==='resetConfirmations'){
    setBusy(true);try{await confirmations.reset();}finally{if(!disposed)setBusy(false);}return;
  }
  if(action==='clearSelection'){selected=null;selectedIds=[];refresh();schedule();return;}
  if(action==='selectSection'){selectedIds=project.placements.filter(p=>p.section===$('section').value).map(p=>p.id);selected=selectedIds.at(-1)||null;refresh();schedule();return;}
  const ids=[...selectedIds],idFactory=()=>crypto.randomUUID();
  if(action==='group')return applyProjectChange(authoring.groupSelection(project,ids,{id:idFactory(),name:String(args[0]||'Group').trim()||'Group'}),'Placements grouped.');
  if(action==='ungroup')return applyProjectChange(authoring.ungroupSelection(project,ids),'Group removed.');
  if(action==='lock'||action==='unlock')return applyProjectChange(authoring.setLocked(project,ids,action==='lock'),action==='lock'?'Selection locked.':'Selection unlocked.');
  if(action==='align'||action==='distribute'){
    let next=action==='align'?authoring.alignSelection(project,ids,args[0],getBounds):authoring.distributeSelection(project,ids,args[0],getBounds);
    if(project.authoring?.links?.length)next=mirror.propagateLinks(project,next,ids).project;
    return applyProjectChange(next,action==='align'?'Selection aligned.':'Selection evenly spaced.');
  }
  if(action==='duplicate'){
    const next=authoring.duplicateSelection(project,ids,{idFactory}),old=new Set(project.placements.map(p=>p.id));
    return applyProjectChange(next,'Selection duplicated.',next.placements.filter(p=>!old.has(p.id)).map(p=>p.id));
  }
  if(action==='remove')return applyProjectChange(authoring.removeSelection(project,ids),'Selection removed.',[]);
  if(action==='replaceColour'){
    const [key,hex,scope]=args;if(!key||!/^#[0-9a-f]{6}$/i.test(hex))return;
    const from=key.split(',').map(Number),to=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
    if(from.every((value,i)=>value===to[i])){message('The replacement colour is unchanged.');return;}
    const affected=scope==='all'?project.placements.map(p=>p.id):ids,used=new Set(project.placements.filter(p=>affected.includes(p.id)).map(p=>p.vinylId));
    const alpha=new Set(project.vinyls.filter(v=>used.has(v.id)).flatMap(v=>v.shapes.filter(s=>!s.mask&&!s.data[6]&&s.color.slice(0,3).every((c,i)=>c===from[i])).map(s=>s.color[3])));
    let next=project;for(const a of alpha)next=authoring.replaceSelectionColor(next,affected,[...from,a],[...to,a],{idFactory});
    next=syncSourceLinks(project,next);
    const spec=confirmationSpec('colour',{project,next,selectedIds:ids,scope,from:'#'+from.map(n=>n.toString(16).padStart(2,'0')).join(''),to:hex});
    if(!spec){message('No matching colours were changed.');return;}
    if(!await confirmOperation(spec))return;
    setBusy(true);try{await applyProjectChange(next,'Design colour replaced.');}finally{if(!disposed)setBusy(false);}return;
  }
  if(action==='createOtherSide'){
    const original=current(),opposite={Left:'Right',Right:'Left',LeftWindow:'RightWindow',RightWindow:'LeftWindow'}[original?.section];
    if(!opposite||!config.sections.some(s=>s.section===opposite))throw Error('Choose a placement on an eligible left or right side.');
    if(locked(original.id))throw Error('Unlock this placement first.');
    const source=project.vinyls.find(v=>v.id===original.vinylId),copy=args[0]==='mirror'?{id:idFactory(),name:source.name,shapes:mirror.reflectArtwork(source.shapes)}:null;
    const placement={...original,id:idFactory(),section:opposite,vinylId:copy?.id||source.id};
    const next={...project,placements:[...project.placements,placement],vinyls:copy?[...project.vinyls,copy]:project.vinyls};
    setBusy(true);try{await applyProjectChange(next,'Other side created. Align it, then select both sides and link the pair.',[placement.id]);$('section').value=opposite;refresh();schedule();}finally{if(!disposed)setBusy(false);}return;
  }
  if(action==='linkMirror'){
    if(ids.length!==2)throw Error('Select the two aligned side placements.');
    const next=mirror.linkPlacements(project,{id:idFactory(),sourceId:selected,targetId:ids.find(id=>id!==selected),mode:args[0]==='mirror'?'mirror-artwork':'readable-lettering',targetVinylId:idFactory()}).project;
    setBusy(true);try{await applyProjectChange(next,'User-aligned sides linked. Editing either side updates its partner.',[selected]);}finally{if(!disposed)setBusy(false);}return;
  }
  if(action==='unlinkMirror'){
    let next=project;for(const link of project.authoring?.links||[])if(ids.includes(link.a)||ids.includes(link.b))next=mirror.unlinkMirror(next,link.id).project;
    return applyProjectChange(next,'Side link removed.');
  }
  if(action==='mirrorMode'){
    let next=project;
    for(const link of project.authoring?.links||[])if(ids.includes(link.a)||ids.includes(link.b))next=mirror.setMirrorLinkMode(next,link.id,args[0]==='mirror'?'mirror-artwork':'readable-lettering',idFactory()).project;
    setBusy(true);try{await applyProjectChange(next,'Linked artwork orientation updated.');}finally{if(!disposed)setBusy(false);}return;
  }
  if(action==='editSource'){
    if(config.source_editor_roundtrip!==true)throw Error('Reopen Studio with the updated backend to edit sources.');
    if(sourceEdit)throw Error('Apply or cancel the pending source edit first.');
    if(ids.length!==1||locked(selected))throw Error('Select one unlocked placement.');
    if(!await confirmOperation(confirmationSpec('source.open',{project,selectedIds:ids})))return;
    const source=project.vinyls.find(v=>v.id===current().vinylId),binding={documentId:sourceDocumentId,sourceId:idFactory(),sourceRevision:0};
    setBusy(true);try{
      const value=await api('source-editor',{...binding,source:{name:source.name.slice(0,120),shapes:source.shapes}});
      if(!/^[a-f0-9]{32}$/.test(value?.id))throw Error('The source editor did not return a valid edit link.');
      sourceEdit={...binding,id:value.id,vinylId:source.id,placementId:selected,status:value.status,customizationWarnings:value.customizationWarnings};
      sourceEditMessage('2D editor opened. Return artwork from its File menu, then check changes here.');
    }finally{if(!disposed)setBusy(false);}return;
  }
  if(action==='checkSourceEdit'){
    if(!sourceEdit)return;const job=sourceEdit,value=await api('source-editor/'+job.id);
    if(disposed||sourceEdit!==job)return;sourceEdit.status=value.status;
    if(Number.isSafeInteger(value.customizationWarnings))sourceEdit.customizationWarnings=value.customizationWarnings;
    sourceEditMessage(value.status==='ready'?t('Returned artwork ready to apply.'):value.error?errorText(value.error):t`Source edit: ${stateLabel(value.status)}`);tools.refresh();return;
  }
  if(action==='cancelSourceEdit'){
    if(!sourceEdit)return;const job=sourceEdit;
    setBusy(true);try{
      await api(`source-editor/${job.id}/cancel`,{});
      if(disposed||sourceEdit!==job)return;
      sourceEdit=null;sourceEditMessage('Edit link cancelled. Your current artwork is unchanged.',job);
    }finally{if(!disposed)setBusy(false);}return;
  }
  if(action==='applySourceEdit'){
    const job=sourceEdit;if(!job)return;
    const origin=project.vinyls.find(v=>v.id===job.vinylId),placement=project.placements.find(p=>p.id===job.placementId);
    if(sourceDocumentId!==job.documentId||!origin||!placement||placement.vinylId!==job.vinylId)throw Error('This document or source changed. Cancel the old link and start another source edit.');
    const affected=args[0]==='selection'?[job.placementId]:project.placements.filter(p=>p.vinylId===job.vinylId).map(p=>p.id);
    if(affected.some(locked))throw Error('Unlock the affected placements first.');
    if(!await confirmOperation(confirmationSpec('source.apply',{project,sourceEdit:job,scope:args[0]})))return;
    setBusy(true);try{
      const result=await api(`source-editor/${job.id}/take`,{documentId:job.documentId,sourceId:job.sourceId,sourceRevision:job.sourceRevision});
      if(disposed||sourceEdit!==job||sourceDocumentId!==job.documentId)throw Error('Source edit was interrupted. Nothing was replaced.');
      const replacement={id:idFactory(),name:origin.name,shapes:result.source?.shapes};
      let next={...project,placements:project.placements.map(p=>affected.includes(p.id)?{...p,vinylId:replacement.id}:p),vinyls:[...project.vinyls,replacement]};
      const used=new Set(next.placements.map(p=>p.vinylId));next.vinyls=next.vinyls.filter(v=>used.has(v.id));next=syncSourceLinks(project,next);
      if(Number.isSafeInteger(result.customizationWarnings))job.customizationWarnings=result.customizationWarnings;
      await applyProjectChange(next,'Returned artwork applied.');sourceEdit=null;diagnostics.emit('action',{action:'source_return',outcome:'ok'});sourceEditMessage('Source updated. Undo restores the previous artwork.',job);
    }finally{if(!disposed)setBusy(false);}return;
  }
  throw Error('Unknown authoring action.');
}
function finishTransform(cancel=false) {
  if(!transform)return false;
  const state=transform;transform=null;snapGuide=null;
  // Native range dragging continues after Escape/Enter until its pointer ends.
  if(state.kind==='slider'&&sliderPointer?.field===state.field)sliderPointer.suppressed=true;
  if(cancel){restore(state.before);diagnostics.emit('action',{action:'cancel',outcome:'cancelled'});}else commit(state.before);
  if(state.kind==='surface')surface?.setMode(surfaceMode);
  message(cancel?'Transform cancelled.':'Transform applied.');return true;
}
function setSurfaceMode(mode) {
  if(!Object.hasOwn(modes,mode)||editBlocked()||disposed)return false;
  surfaceMode=mode;surface?.setMode(mode);refresh();return true;
}
function markAll() { config.sections.forEach(s => dirtySections.add(s.section)); schedule(); }
function fingerprint() { return JSON.stringify({vinylIds:project.vinyls.map(v=>v.id),placements:project.placements,vehicle_parts:project.vehicle_parts||{},authoring:project.authoring||null}); }
function changed() { return numericEdited.size>0||fingerprint() !== saved; }
function setBusy(value) { busy = value; refresh(); }
function pruneSources() {
  const retained=history.retainedVinylIds(); project.vinyls.forEach(v=>retained.add(v.id));
  for(const id of sources.keys())if(!retained.has(id)){sources.delete(id);const image=images.get(id);if(image)image.src='';images.delete(id);}
}
function commit(before) { history.push(before, snapshot()); pruneSources(); refresh();recovery?.changed();diagnostics.emit('action',{action:'edit',outcome:'ok',...projectCounts(project,config.sections.length)}); }
function restore(state) {
  if (!state) return;
  const requested=state.vehicle_parts||{},existing=currentVehicleParts();
  const parts=!canPreview()?structuredClone(requested):JSON.stringify(existing)===JSON.stringify(requested)?existing:setVehicleParts(requested);
  project.vinyls=state.vinylIds.map(id=>{const source=sources.get(id);if(!source)throw Error('Undo source is unavailable.');return source;});
  project.placements = structuredClone(state.placements); selected = state.selected;selectedIds=[...(state.selectedIds||[selected].filter(Boolean))];
  if(state.authoring)project.authoring=structuredClone(state.authoring);else delete project.authoring;
  retainParts(parts);
  if(current()) { $('section').value=current().section; pickedSource=current().vinylId; }
  pruneSources(); markAll(); refresh();recovery?.changed();
}
function restoreHistory(action) {
  const state=history[action](snapshot());
  restore(state);
  if(state)diagnostics.emit('action',{action,outcome:'ok',...projectCounts(project,config.sections.length)});
}
function icon(button) {
  const nodes = window.KfpsIconNodes?.[button.dataset.icon]; if (!nodes) return;
  const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
  for (const [key, value] of Object.entries({ viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':'1.8', 'stroke-linecap':'round', 'stroke-linejoin':'round', 'aria-hidden':'true' })) svg.setAttribute(key, value);
  for (const [tag, attrs] of nodes) { const node = document.createElementNS(ns, tag); Object.entries(attrs).forEach(([k,v]) => node.setAttribute(k,v)); svg.append(node); }
  button.prepend(svg);
}
document.querySelectorAll('[data-icon]').forEach(icon);
async function responseError(response) {
  const raw=await response.text();
  let reason=raw,value;
  try {value=JSON.parse(raw);if(typeof value.error==='string')reason=value.error;} catch {}
  return Object.assign(Error(errorText(reason.slice(0,4096))||t`Request failed (HTTP ${response.status}).`),{status:response.status,code:value?.code,entry:value?.entry});
}
async function api(path, value) {
  try {
    const response = await fetch(`./api/${path}`, { signal: stop.signal, ...(value === undefined ? {} : { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(value) }) });
    if (!response.ok) { diagnostics.emit('error',{error_code:response.status>=500?'http_5xx':'http_4xx',http_status:response.status});throw await responseError(response); }
    return await response.json();
  } catch(error) { if(!error.status)diagnostics.emit('error',{error_code:stop.signal.aborted?'aborted':'network'});throw error; }
}
async function raster(shapes) {
  const result = await api('render-vinyl', { shapes });
  if (typeof result.png !== 'string' || !result.png.startsWith('data:image/png;base64,')) throw Error('The vinyl preview is invalid.');
  const image = new Image(); image.src = result.png; await image.decode();
  if (image.width !== 2048 || image.height !== 1024) throw Error('The vinyl preview has unexpected dimensions.');
  image.artworkBounds = result.bounds;
  if (disposed) throw Error('The editor is closed.');
  return image;
}
function drawSection(name) {
  let surface = sectionCanvases.get(name);
  if (!surface) { surface = document.createElement('canvas'); surface.width = 2048; surface.height = 1024; sectionCanvases.set(name, surface); }
  const ctx = surface.getContext('2d'); ctx.setTransform(1,0,0,1,0,0); ctx.clearRect(0,0,2048,1024);
  for (const p of project.placements) {
    if (p.section !== name || !p.visible || !images.has(p.vinylId)) continue;
    ctx.save(); ctx.setTransform(...placementMatrix(p)); ctx.globalAlpha = p.opacity;
    ctx.drawImage(images.get(p.vinylId), -1024, -512); ctx.restore();
  }
  return surface;
}
function paintSection(section) {
  const surface = drawSection(section.section), region = section.paint_region;
  const [x,y,w,h] = [region[0]*atlas.width,region[1]*atlas.height,(region[2]-region[0])*atlas.width,(region[3]-region[1])*atlas.height];
  atlasContext.save(); atlasContext.setTransform(1,0,0,1,0,0); atlasContext.clearRect(x-8,y-8,w+16,h+16);
  atlasContext.beginPath(); atlasContext.rect(x,y,w,h); atlasContext.clip();
  atlasContext.setTransform(...sectionToPaint(section, config.paint_size)); atlasContext.drawImage(surface,0,0); atlasContext.restore();
  // Replicate the boundary gutter used by the existing packed-paint contract.
  for (const [sx,sy,sw,sh,dx,dy,dw,dh] of [[x,y,1,h,x-8,y,8,h],[x+w-1,y,1,h,x+w,y,8,h],[x,y,w,1,x,y-8,w,8],[x,y+h-1,w,1,x,y+h,w,8],
    [x,y,1,1,x-8,y-8,8,8],[x+w-1,y,1,1,x+w,y-8,8,8],[x,y+h-1,1,1,x-8,y+h,8,8],[x+w-1,y+h-1,1,1,x+w,y+h,8,8]]) atlasContext.drawImage(atlas,sx,sy,sw,sh,dx,dy,dw,dh);
}
function drawSelection() {
  sectionContext.setTransform(1,0,0,1,0,0); sectionContext.clearRect(0,0,2048,1024);
  const surface = sectionCanvases.get($('section').value); if (surface) sectionContext.drawImage(surface,0,0);
  const theme=getComputedStyle(document.documentElement);
  if(snapGuide){sectionContext.save();sectionContext.strokeStyle=theme.getPropertyValue('--accent').trim();sectionContext.lineWidth=3;sectionContext.setLineDash([10,8]);sectionContext.beginPath();
    if(snapGuide.guideX!==null){sectionContext.moveTo(snapGuide.guideX,0);sectionContext.lineTo(snapGuide.guideX,1024);}
    if(snapGuide.guideY!==null){sectionContext.moveTo(0,snapGuide.guideY);sectionContext.lineTo(2048,snapGuide.guideY);}
    sectionContext.stroke();sectionContext.restore();}
  for(const placement of project.placements.filter(p=>selectedIds.includes(p.id)&&p.section===$('section').value)){
    sectionContext.save(); sectionContext.setTransform(...placementMatrix(placement));
    sectionContext.strokeStyle=theme.getPropertyValue('--editor-selection-border').trim();sectionContext.lineWidth=8/Math.max(placement.scaleX,placement.scaleY);sectionContext.setLineDash([22,12]);
    const bounds=images.get(placement.vinylId)?.artworkBounds;
    if(bounds)sectionContext.strokeRect(bounds[0]-1024,bounds[1]-512,bounds[2]-bounds[0],bounds[3]-bounds[1]);
    sectionContext.restore();
  }
  const p=current();if(!p||p.section!==$('section').value)return;
  const point = mapPoint(placementMatrix(p),0,0); sectionContext.strokeStyle=theme.getPropertyValue('--text').trim(); sectionContext.lineWidth=6;
  sectionContext.beginPath(); sectionContext.moveTo(point[0]-20,point[1]); sectionContext.lineTo(point[0]+20,point[1]);
  sectionContext.moveTo(point[0],point[1]-20); sectionContext.lineTo(point[0],point[1]+20); sectionContext.stroke();
}
function schedule() {
  if (queued || disposed || !canPreview()) return;
  queued = requestAnimationFrame(() => {
    queued = 0; if (disposed || !canPreview()) return;
    const start = performance.now();
    for (const section of config.sections) if (dirtySections.has(section.section)) paintSection(section);
    if (dirtySections.size && isSceneReady()) { updatePaintCanvas(atlas); metrics.paintUpdates++; }
    dirtySections.clear(); drawSelection();
    if(drag||transform)surface?.refresh();
    metrics.lastComposeMs=performance.now()-start; metrics.maxComposeMs=Math.max(metrics.maxComposeMs,metrics.lastComposeMs);
  });
}
function drawThumbnail(canvas,image) {
  const ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);
  const bounds=image?.artworkBounds||[0,0,image?.width||0,image?.height||0];
  const width=bounds[2]-bounds[0],height=bounds[3]-bounds[1];
  if(image&&width>0&&height>0){const scale=Math.min((canvas.width-8)/width,(canvas.height-8)/height);ctx.drawImage(image,bounds[0],bounds[1],width,height,(canvas.width-width*scale)/2,(canvas.height-height*scale)/2,width*scale,height*scale);}
}
function artworkButton(source,detail) {
  const button=document.createElement('button');button.type='button';
  const thumbnail=document.createElement('canvas');thumbnail.className='art-thumbnail';thumbnail.width=100;thumbnail.height=72;thumbnail.setAttribute('aria-hidden','true');drawThumbnail(thumbnail,images.get(source.id));
  const caption=document.createElement('span');caption.className='art-caption';
  const name=document.createElement('span');name.className='art-name';name.textContent=source.name;
  const description=document.createElement('span');description.className='art-detail';description.textContent=detail;
  caption.append(name,description);button.append(thumbnail,caption);return button;
}
function refreshSources(blocked) {
  if(!project.vinyls.some(v=>v.id===pickedSource))pickedSource=current()?.vinylId||project.vinyls[0]?.id||null;
  const picker=$('vinylSource'),signature=JSON.stringify(project.vinyls.map(v=>[v.id,v.name]));
  if(signature!==sourceSignature) {
    sourceSignature=signature;picker.replaceChildren();$('sourceList').replaceChildren();sourceButtons.clear();
    if(!project.vinyls.length) {
      const option=document.createElement('option');option.value='';option.textContent=t('No vinyl sources');picker.append(option);
    }
    for(const source of project.vinyls) {
      const option=document.createElement('option');option.value=source.id;option.textContent=source.name;picker.append(option);
      const button=artworkButton(source,t`${source.shapes.length} shapes`);button.className='source-item';button.dataset.source=source.id;button.title=t`Select ${source.name}`;
      button.addEventListener('click',()=>{if(interactionBusy())return;pickedSource=source.id;refreshSources(false);});
      $('sourceList').append(button);sourceButtons.set(source.id,button);
    }
  }
  for(const [id,button] of sourceButtons){button.disabled=blocked;button.setAttribute('aria-pressed',String(id===pickedSource));}
  picker.value=pickedSource||'';picker.disabled=blocked||!pickedSource;
  $('placeSource').disabled=blocked||!canPreview()||!pickedSource||project.placements.length>=MAX_PLACEMENTS;
  $('exportSource').disabled=blocked||!pickedSource;
  $('placeSource').title=project.placements.length>=MAX_PLACEMENTS?t`The ${MAX_PLACEMENTS}-placement limit is reached`:t`Place this vinyl at the center of ${sectionLabel($('section').value)}`;
  const preview=$('sourcePreview'),image=images.get(pickedSource),source=project.vinyls.find(v=>v.id===pickedSource);
  drawThumbnail(preview,image);
  preview.setAttribute('aria-label',source?t`${source.name} source preview`:t('No vinyl source selected'));
  $('sourceInfo').textContent=source?t`${source.shapes.length} shapes / ${project.placements.filter(p=>p.vinylId===source.id).length} uses`:t('0 sources');
}
function refresh() {
  if (!project) return;
  normaliseSelection();
  const blocked=interactionBusy(),editingBlocked=blocked||!canPreview();
  $('chooseCar').disabled=blocked||config.car_switch!==true;
  $('chooseCar').title=t(config.car_switch===true?'Choose another car from the configured local installation':'Car switching is unavailable in this session');
  if($('carPicker').open||carWorking)refreshCars();
  $('retryHostTransfer').disabled=editingBlocked||handoffWorking;
  for(const [mode,label] of Object.entries(modes)){const button=$('mode'+label);button.disabled=editingBlocked;button.setAttribute('aria-pressed',String(surfaceMode===mode));}
  for(const id of ['reset','rotate','wheels'])$(id).disabled=editingBlocked;
  document.querySelectorAll('.section-strip button').forEach(button=>{button.disabled=editingBlocked;});
  $('reloadPreview').disabled=blocked||changed();
  $('saveRecovery').disabled=saveWorking||blocked&&!previewError;
  $('reloadPreview').title=t(changed()?'Save the layout before reloading':'Reload the preview, then reopen your saved layout');
  $('rotate').hidden=surfaceMode!=='orbit';
  const transformLabel=transform?.kind==='slider'?t({x:'X',y:'Y',scaleX:'Scale X',scaleY:'Scale Y',rotation:'Rotation (deg)',skew:'Skew',opacity:'Opacity'}[numeric[transform.field]]):t(modes[surfaceMode]);
  $('toolState').textContent=transform?t`${transformLabel} / Transform preview`:surfaceMode==='orbit'?t('Orbit'):`${t(modes[surfaceMode])} / ${selectedIds.length?t`${selectedIds.length} selected`:t('No selection')}`;
  $('transformActions').hidden=!transform&&!drag;$('applyTransform').disabled=!transform&&!drag;$('cancelTransform').disabled=!transform&&!drag;
  document.querySelectorAll('#parts select').forEach(select=>{select.disabled=editingBlocked;});
  $('undo').disabled=editingBlocked||!history.canUndo; $('redo').disabled=editingBlocked||!history.canRedo;
  $('importVinyl').disabled=editingBlocked; $('openProject').disabled=editingBlocked; $('saveProject').disabled=saveWorking||blocked&&!previewError;
  const experiment=config.experimental_export;
  $('openSaveArtwork').disabled=editingBlocked||experiment?.template_layout_available!==true;
  const componentBlocked=nonstockPreview();
  $('resetParts').disabled=editingBlocked||!componentBlocked;
  $('exportExperiment').disabled=blocked||componentBlocked||experiment?.enabled!==true||!project.placements.length;
  const reason=errorText(typeof experiment?.reason==='string'?experiment.reason:'No save template supplied.');
  const templateReason=typeof experiment?.template_layout_reason==='string'&&experiment.template_layout_reason.trim()?errorText(experiment.template_layout_reason):reason||t('Save artwork is unavailable.');
  $('openSaveArtwork').title=experiment?.template_layout_available===true?t('Open artwork from the read-only save template'):templateReason;
  $('exportExperiment').title=componentBlocked?t(componentExportReason):experiment?.enabled!==true?reason||t('Experimental export is unavailable.'):t(!project.placements.length?'Add at least one placement before exporting':'Download an experimental ZIP for isolated testing');
  const count=Number.isInteger(experiment?.template_shape_count)&&experiment.template_shape_count>=0?experiment.template_shape_count:null;
  $('experimentStatus').textContent=experimentNotice||(experiment?.template_layout_available!==true?templateReason:experiment?.enabled===true?t`Save template${count===null?'':t`: ${count} shapes`}. Game acceptance is unverified.`:reason||t('Experimental export is unavailable.'));
  if(componentBlocked)$('experimentStatus').textContent+=' '+t(componentExportReason);
  $('experimentStatus').classList.toggle('error',experimentError);
  $('section').disabled=blocked;
  const p=current(),selectionLocked=selectedIds.some(locked); $('properties').disabled=!canPreview()||busy||saveWorking||!!drag||transform?.kind==='surface'||!p||selectionLocked;
  $('selectionName').textContent=p?project.vinyls.find(v=>v.id===p.vinylId).name:t('No vinyl selected');
  refreshTransformFields();
  $('documentState').textContent=t(changed()?'Unsaved layout':'Saved layout');
  for(const id of Object.keys(numeric)){ $(id).disabled=blocked||selectionLocked;$(id+'Range').disabled=selectionLocked||blocked&&!(transform?.kind==='slider'&&transform.field===id); }
  $('aspectLock').disabled=blocked;$('visible').disabled=blocked;$('placementSection').disabled=blocked;$('remove').disabled=blocked||!p;
  $('placementSection').value=p?.section||$('section').value;
  $('visible').checked=!!p?.visible;
  $('duplicate').disabled=blocked||!p||project.placements.length>=MAX_PLACEMENTS;
  $('backward').disabled=blocked||placementStepIndex(project.placements,selected,-1)<0;
  $('forward').disabled=blocked||placementStepIndex(project.placements,selected,1)<0;
  refreshSources(blocked);
  const onSection=project.placements.filter(item=>item.section===$('section').value);
  refreshSectionCount();
  $('exportSection').disabled=blocked||config.section_vinyl_export!==true||!onSection.some(item=>item.visible&&item.opacity>0);
  $('exportSection').title=config.section_vinyl_export!==true?t('Section vinyl export is unavailable in this backend'):t`Export visible artwork on ${sectionLabel($('section').value)} as one native vinyl JSON (maximum ${MAX_NATIVE_VINYL_SHAPES} shapes)`;
  $('sectionEmpty').hidden=onSection.some(item=>item.visible&&item.opacity>0);
  $('sectionEmpty').textContent=onSection.length?t('No visible placements on this section.'):t`No placements on ${sectionLabel($('section').value)}.`;
  $('counts').textContent=t`${project.placements.length} placements / ${project.vinyls.length} vinyl sources`;
  $('vehicle').textContent=t`${config.vehicle.model_code} / Car ${config.vehicle.car_id} / ${project.placements.length} placements`;
  const list=$('placementList'),signature=JSON.stringify([project.placements.map(p=>[p.id,p.vinylId,p.section,p.visible]),project.authoring||null]);
  if(signature!==placementSignature) {
    placementSignature=signature;list.replaceChildren();placementButtons.clear();
    if(!project.placements.length) { const empty=document.createElement('p');empty.className='list-empty';empty.textContent=t('No placements');list.append(empty); }
    for(const placement of [...project.placements].reverse()) {
      const source=project.vinyls.find(v=>v.id===placement.vinylId),group=project.authoring?.groups?.find(g=>g.placements.includes(placement.id));
      const button=artworkButton(source,sectionLabel(placement.section)+(group?` / ${group.name}`:'')+(locked(placement.id)?t(' / Locked'):'')+(placement.visible?'':t(' / Hidden')));
      button.className='placement';button.dataset.placement=placement.id;
      button.title=t`${source.name} on ${sectionLabel(placement.section)}. Ctrl/Shift-click adds to selection; Alt-click selects one group member.`;
      button.addEventListener('click',event=>selectPlacement(placement.id,undefined,{additive:event.ctrlKey||event.metaKey||event.shiftKey,individual:event.altKey}));list.append(button);placementButtons.set(placement.id,button);
    }
  }
  for(const [id,button] of placementButtons){button.disabled=blocked;button.setAttribute('aria-pressed',String(selectedIds.includes(id)));button.dataset.selected=String(selectedIds.includes(id));button.dataset.locked=String(locked(id));}
  tools?.refresh();recovery?.refresh();inspection?.refresh();
  if(canPreview())surface?.refresh();
}
function createPlacement(vinylId, vinyls=project.vinyls) {
  return makePlacement({...project,vinyls},vinylId,$('section').value,config.sections.map(s=>s.section),crypto.randomUUID());
}
function placeSource() {
  if(editBlocked()||!flushNumeric())return;
  try {
    const placement=createPlacement(pickedSource);
    serializeProject({...project,placements:[...project.placements,placement]});
    edit(()=>{project.placements.push(placement);selected=placement.id;});
    message(t`Vinyl placed on ${sectionLabel(placement.section)}.`);
  } catch(error) { message(error.message,true); }
}
async function importFile(file,options={}) {
  requirePreview();
  if(!file) return; if(file.size>8*1024*1024) throw Error('The vinyl JSON exceeds 8 MiB.');
  if(project.vinyls.length>=MAX_VINYLS) throw Error(t`The ${MAX_VINYLS}-source limit is reached. Existing vinyl sources can still be reused.`);
  if(project.placements.length>=MAX_PLACEMENTS) throw Error('The placement limit is reached.');
  const raw=JSON.parse(await file.text()), shapes=Array.isArray(raw)?raw:raw?.shapes;
  if(!Array.isArray(shapes))throw Error('The vinyl JSON must contain a native shapes array or an object with a shapes array.');
  const image=await raster(shapes);try{requirePreview();}catch(error){image.src='';throw error;}
  if(options.isCurrent&&!options.isCurrent()){image.src='';return;}
  const before=snapshot(), id=crypto.randomUUID();
  const source={id,name:file.name.replace(/\.json$/i,'').slice(0,160)||'Vinyl',shapes};
  const placement=createPlacement(id,[...project.vinyls,source]);
  serializeProject({...project,vinyls:[...project.vinyls,source],placements:[...project.placements,placement]});
  sources.set(id,source);project.vinyls.push(source); images.set(id,image);project.placements.push(placement);selected=placement.id;pickedSource=id;dirtySections.add(placement.section);schedule();commit(before);
  message('Vinyl added.');
  diagnostics.emit('action',{action:'import',outcome:'ok',...projectCounts(project,config.sections.length)});
}
async function confirmReplace() {
  if(!changed()) return true;
  const dialog=$('confirmOpen'); dialog.returnValue='cancel'; dialog.showModal();
  return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='replace'),{once:true}));
}
async function confirmExperiment() {
  const dialog=$('confirmExperiment');dialog.returnValue='cancel';dialog.showModal();
  return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue==='export'),{once:true}));
}
function beginExternalPicker(kind,options={}) {
  if(disposed||interactionBusy())return;
  const documentId=sourceDocumentId,revision=fingerprint();
  externalPicker={kind,isCurrent:()=>sourceDocumentId===documentId&&fingerprint()===revision&&(!options.isCurrent||options.isCurrent())};
  refresh();
  try{$(kind==='project'?'projectFile':'vinylFile').click();}
  catch(error){externalPicker=null;refresh();message(error.message,true);}
}
async function completeExternalPicker(kind,cancel=false) {
  const input=$(kind==='project'?'projectFile':'vinylFile'),file=input.files?.[0],pending=externalPicker?.kind===kind?externalPicker:null;
  input.value='';if(pending)externalPicker=null;refresh();
  if(disposed||cancel||!file){diagnostics.emit('action',{action:'cancel',outcome:'cancelled'});return;}
  if(interactionBusy()){message('Finish the current edit, then choose the file again.',true);return;}
  if(pending&&!pending.isCurrent()){message('The current layout changed. Nothing was opened.',true);return;}
  const options=pending?{isCurrent:pending.isCurrent}:{};
  await run(()=>kind==='project'?openFile(file,options):importFile(file,options))();
}
async function openFile(file,options={}) {
  requirePreview();
  if(!file) return; if(file.size>32*1024*1024) throw Error('The project exceeds 32 MiB.');
  const next=validateProject(JSON.parse(await file.text()),config.vehicle,config.sections.map(s=>s.section));
  const parts=validatePartConfiguration(next.vehicle_parts);
  serializeProject(next);
  const nextImages=new Map();
  try {for(const vinyl of next.vinyls) nextImages.set(vinyl.id,await raster(vinyl.shapes));}
  catch(error) {for(const image of nextImages.values())image.src='';throw error;}
  try {if(disposed)throw Error('The editor is closed.');if(options.isCurrent&&!options.isCurrent())throw Error(options.recovery?'The current layout changed. Recovery was not applied.':'The current layout changed. Nothing was opened.');requirePreview();setVehicleParts(parts);}
  catch(error){for(const image of nextImages.values())image.src='';throw error;}
  project=next; for(const image of images.values())image.src='';images.clear();sources.clear();
  sourceSignature=placementSignature='';
  for(const vinyl of next.vinyls)sources.set(vinyl.id,vinyl);for(const [key,image] of nextImages) images.set(key,image);
  selected=next.placements[0]?.id||null;pickedSource=current()?.vinylId||next.vinyls[0]?.id||null; if(current()) $('section').value=current().section;
  retainParts(parts);
  selectedIds=authoring.selectionIds(project,selected?[selected]:[],{expandGroups:true});sourceDocumentId=crypto.randomUUID();
  history.reset(); saved=options.recovery?'':fingerprint();markAll();refresh();
  projectStorage?.adopt(null);
  if(!options.recovery)recovery?.changed({newDocument:true});
  message(next.vehicle_parts?'Layout and component configuration reopened.':'Layout reopened with the initial component configuration; no component overrides were stored.');
  diagnostics.emit('action',{action:options.recovery?'recovery':'reopen',outcome:'ok',...projectCounts(project,config.sections.length)});
}
function nativeDownloadFinished(url,result) {
  const pending=nativeDownloads.get(url);
  if(!pending||!result||!['completed','cancelled','failed'].includes(result.status))return;
  nativeDownloads.delete(url);URL.revokeObjectURL(url);
  if(result.status==='failed')pending.reject(Error(typeof result.message==='string'&&result.message.trim()?result.message.slice(0,512):'The file could not be saved. Try a writable location.'));
  else pending.resolve(result.status==='completed');
}
if(window.__kfpsStudioNativeDownloads===true)window.__kfpsStudioDownloadFinished=nativeDownloadFinished;
async function downloadBlob(blob,filename) {
  if(disposed)return false;
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');link.href=url;link.download=filename;
  if(window.__kfpsStudioNativeDownloads===true){
    // Keep the Blob alive while Qt's file picker is open; only disk completion is a save.
    return new Promise((resolve,reject)=>{
      nativeDownloads.set(url,{resolve,reject});
      try{link.click();}catch(error){nativeDownloads.delete(url);URL.revokeObjectURL(url);reject(error);}
    });
  }
  try{link.click();return true;}finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
}
async function downloadProject() {
  const document=project,checkpoint=fingerprint();
  const validated=validateProject(project,config.vehicle,config.sections.map(s=>s.section));
  if(projectStorage){
    const result=await projectStorage.save();
    if(disposed||project!==document)return false;
    if(!result){message('Save cancelled. Your layout is unchanged.');return false;}
    saved=checkpoint;refresh();message('Layout project saved.');return true;
  }
  const completed=await downloadBlob(new Blob([serializeProject(validated)],{type:'application/json'}),`${config.vehicle.model_code}.kfps-layout.json`);
  if(disposed||project!==document)return false;
  if(!completed){message('Save cancelled. Your layout is unchanged.');return false;}
  saved=checkpoint;refresh();message(window.__kfpsStudioNativeDownloads===true?'Layout project saved.':'Layout download started. Check Chrome downloads for completion.');
  return true;
}
async function saveProject() {
  if(saveWorking||(interactionBusy()&&!previewError)||disposed)return;
  const pending=numericEdited.values().next().value;
  if(!previewError&&pending&&!commitNumeric(pending))return;
  saveWorking=true;refresh();
  const started=performance.now();diagnostics.emit('action',{action:'save',outcome:'start'});
  try{const complete=await downloadProject();diagnostics.emit('action',{action:'save',outcome:complete?(projectStorage||window.__kfpsStudioNativeDownloads===true?'ok':'requested'):'cancelled',duration_ms:performance.now()-started});}catch(error){diagnostics.emit('action',{action:'save',outcome:'error'});if(!disposed)message(error.message,true);}finally{saveWorking=false;if(!disposed)refresh();}
}

function carMessage(text,error=false) { $('carStatus').textContent=error?errorText(text):t(text);$('carStatus').classList.toggle('error',error); }
function refreshCars() {
  $('carSearch').disabled=carWorking||!!carJob;
  $('switchCar').disabled=carWorking||!!carJob||!carPicked||carPicked===carCurrent;
  $('retryCarStatus').hidden=!carJob||carWorking;
  $('closeCarPicker').hidden=!carJob||carWorking;
  $('cancelCarSwitch').disabled=carCommitting||carWorking&&carCancelRequested;
  $('cancelCarSwitch').textContent=t(carWorking||carJob?'Cancel preparation':'Close');
  $('carCurrent').textContent=t`Current car: ${config.vehicle.model_code} / ${config.vehicle.car_id}`;
  for(const button of $('carResults').children)if(button.tagName==='BUTTON'){
    button.disabled=carWorking||!!carJob||button.dataset.car===carCurrent;
    button.setAttribute('aria-pressed',String(button.dataset.car===carPicked));
  }
}
function renderCars() {
  const query=$('carSearch').value.trim().toLowerCase();
  const matches=carCatalogue.filter(car=>`${car.name} ${car.model_code} ${car.car_id??''}`.toLowerCase().includes(query));
  if(!matches.some(car=>car.id===carPicked))carPicked=null;
  const list=$('carResults');list.replaceChildren();list.scrollTop=0;
  for(const car of matches) {
    const button=document.createElement('button');button.type='button';button.dataset.car=car.id;button.className='car-choice';
    button.setAttribute('aria-pressed',String(car.id===carPicked));
    const name=document.createElement('strong');name.textContent=car.name;
    const detail=document.createElement('span');detail.textContent=`${car.model_code} / ${car.car_id??t('Unknown car ID')}${car.id===carCurrent?t(' / Current car'):''}`;
    button.append(name,detail);button.addEventListener('click',()=>{
      if(carWorking||carJob||car.id===carCurrent)return;carPicked=car.id;refreshCars();
    });list.append(button);
  }
  $('carResultCount').textContent=t`${matches.length} cars`;
  if(!matches.length){const empty=document.createElement('p');empty.className='list-empty';empty.textContent=t('No cars match this search.');list.append(empty);}
  refreshCars();
}
async function chooseCar() {
  if(interactionBusy()||disposed||config.car_switch!==true||!flushNumeric())return;
  $('carPicker').showModal();
  if(carJob){carMessage('Preparation status is unresolved. Retry status or cancel before choosing another car.',true);refreshCars();return;}
  carWorking=true;carCancelRequested=false;setBusy(true);carMessage('Reading local car catalogue...');
  try {
    const value=await api('cars');
    if(disposed)return;
    if(value?.enabled!==true||!Array.isArray(value.cars)||value.cars.length>4096)throw Error('The car catalogue is unavailable.');
    const ids=new Set();
    const cars=value.cars.map(car=>{
      if(!car||!(/^[a-f0-9]{32}$/).test(car.id)||ids.has(car.id)||typeof car.name!=='string'||!car.name.trim()||car.name.length>240
        ||typeof car.model_code!=='string'||!car.model_code.trim()||car.model_code.length>160||/[\x00-\x1f]/.test(car.name+car.model_code)
        ||!(car.car_id===null||Number.isSafeInteger(car.car_id)&&car.car_id>=0))throw Error('The car catalogue contains invalid entries.');
      ids.add(car.id);return {id:car.id,name:car.name,model_code:car.model_code,car_id:car.car_id};
    });
    if(value.current!==null&&!ids.has(value.current))throw Error('The current car is missing from the catalogue.');
    carCatalogue=cars;carCurrent=value.current;carPicked=null;$('carSearch').value='';renderCars();
    carMessage(cars.length?'Choose a car. The current layout stays intact until the new car is ready.':'No car archives were found in the configured installation.');
  } catch(error){if(!disposed){carCatalogue=[];carPicked=null;renderCars();carMessage(error.message,true);}}
  finally{carWorking=false;if(!disposed)setBusy(false);}
}
async function confirmCarReplacement() {
  if(!changed())return 'discard';
  const dialog=$('confirmCarSwitch');dialog.returnValue='cancel';dialog.showModal();
  return new Promise(resolve=>dialog.addEventListener('close',()=>resolve(dialog.returnValue),{once:true}));
}
function carJobValue(value,expectedId=null) {
  if(!value||!(/^[a-f0-9]{32}$/).test(value.id)||(expectedId&&value.id!==expectedId)||!['preparing','ready','cancelling','cancelled','failed','committed'].includes(value.status))throw Error('The car preparation returned an invalid status. Your layout is retained.');
  return {id:value.id,status:value.status,error:typeof value.error==='string'?value.error.slice(0,1024):''};
}
async function waitForCar() {
  await new Promise(resolve=>{const done=()=>{clearTimeout(timer);stop.signal.removeEventListener('abort',done);resolve();};const timer=setTimeout(done,500);stop.signal.addEventListener('abort',done,{once:true});});
}
async function followCarJob() {
  let cancellationSent=carJob.status==='cancelling';
  while(!disposed) {
    if(carCancelRequested&&!cancellationSent){carJob=carJobValue(await api(`car-switch/${carJob.id}/cancel`,{}),carJob.id);cancellationSent=true;}
    if(disposed)return;
    if(carJob.status==='cancelled'){carJob=null;carMessage('Car preparation cancelled. The previous layout is unchanged.');return;}
    if(carJob.status==='failed'){const reason=carJob.error||'Car preparation failed. The previous layout is unchanged.';carJob=null;throw Error(reason);}
    if(carJob.status==='ready') {
      if(carCancelRequested)throw Error('Cancellation was not confirmed. Retry status or cancel again.');
      carCommitting=true;refreshCars();carMessage('Opening the prepared car...');
      const value=await api(`car-switch/${carJob.id}/commit`,{});
      if(disposed)return;
      const result=carJobValue(value,carJob.id),url=new URL(value.url,window.location.href);
      if(result.status!=='committed'||typeof value.url!=='string'||url.origin!==window.location.origin||url.username||url.password||url.search||url.hash
        ||!(/^\/[A-Za-z0-9_-]{32,128}\/$/).test(url.pathname)||url.pathname===window.location.pathname)throw Error('The car switch returned an invalid destination. Save your retained layout before reopening the Studio.');
      navigationAuthorized=true;
      try{window.location.assign(url.href);}catch(error){navigationAuthorized=false;throw error;}
      return;
    }
    if(carJob.status==='committed')throw Error('This car session has already switched. Save your retained layout, then reopen the Studio from KFPS.');
    carMessage(carJob.status==='cancelling'?'Cancelling preparation...':'Preparing car geometry and paint surfaces...');
    await waitForCar();if(disposed)return;
    carJob=carJobValue(await api(`car-switch/${carJob.id}`),carJob.id);
  }
}
async function switchCar(resume=false) {
  if(interactionBusy()||disposed||config.car_switch!==true||carWorking)return;
  if(resume?!carJob:carJob||!carCatalogue.some(car=>car.id===carPicked&&car.id!==carCurrent))return;
  carWorking=true;carCommitting=false;setBusy(true);
  try {
    if(!resume) {
      carCancelRequested=false;
      const choice=await confirmCarReplacement();
      if(disposed||!['save','discard'].includes(choice))return;
      if(choice==='save'&&!await downloadProject()){if(!disposed)carMessage('Save cancelled. The current car and layout are unchanged.');return;}
      if(disposed||carCancelRequested)return;
      carMessage('Starting car preparation...');
      carJob=carJobValue(await api('car-switch',{carId:carPicked}));
    }
    await followCarJob();
  } catch(error){if(!disposed)carMessage(t`${errorText(error)} The current layout remains available to save.`,true);}
  finally{carWorking=false;carCommitting=false;if(!disposed)setBusy(false);}
}
function cancelCarSwitch() {
  if(carCommitting)return;
  if(carWorking||carJob){carCancelRequested=true;carMessage('Cancellation requested...');refreshCars();if(!carWorking)void switchCar(true);}
  else $('carPicker').close();
}
async function exportSource() {
  if(disposed)return;
  const source=project.vinyls.find(v=>v.id===pickedSource);if(!source)return;
  let json=JSON.stringify({shapes:source.shapes},null,2);
  if(new TextEncoder().encode(json).byteLength>8*1024*1024)json=JSON.stringify({shapes:source.shapes});
  if(new TextEncoder().encode(json).byteLength>8*1024*1024)throw Error('The source exceeds the 8 MiB vinyl JSON limit.');
  const stem=source.name.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/[. ]+$/g,'').slice(0,100)||'vinyl';
  if(!await downloadBlob(new Blob([json],{type:'application/json'}),`${stem}.vinyl.json`)){if(!disposed)message('Vinyl export cancelled.');return;}
  if(disposed)return;
  message('Original vinyl source downloaded. Placement transforms are not baked into it.');
}
function handoffMessage(text,error=false,retry=false) {
  $('hostTransfer').hidden=false;$('hostTransferMessage').textContent=error?errorText(text):t(text);
  $('hostTransferMessage').classList.toggle('error',error);$('retryHostTransfer').hidden=!retry;
}
async function importHostVinyl() {
  const hash=window.location?.hash||'';
  if(!hash.startsWith('#vinyl')||handoffWorking||disposed)return;
  const match=/^#vinyl=([a-f0-9]{32})$/.exec(hash);
  if(!match){handoffMessage('The incoming vinyl link is invalid. Use Add vinyl to import its JSON file.',true);return;}
  const id=match[1];
  const clearFragment=()=>{if(window.location.hash===hash)window.history.replaceState(window.history.state,'',window.location.pathname+window.location.search);};
  if(completedHandoffs.has(id)){clearFragment();return;}
  if(config.host_vinyl_handoff!==true){handoffMessage('This session cannot receive editor vinyls. Use Add vinyl to import its JSON file.',true,true);return;}
  if(!canPreview()){handoffMessage('Save the current layout and reload the preview before importing the incoming vinyl.',true,true);return;}
  if(interactionBusy()){handoffMessage('Finish the current edit, then retry the incoming vinyl.',false,true);return;}
  if(!flushNumeric()){handoffMessage('Correct or cancel the numeric draft, then retry the incoming vinyl.',true,true);return;}
  handoffWorking=true;setBusy(true);handoffMessage('Importing editor vinyl...');
  try {
    const response=await fetch(`./api/host-vinyl/${id}`,{signal:stop.signal});
    if(!response.ok)throw await responseError(response);
    if(response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!=='application/json')throw Error('The incoming vinyl response is not JSON.');
    const raw=await response.text();
    if(new TextEncoder().encode(raw).byteLength>8*1024*1024)throw Error('The incoming vinyl exceeds 8 MiB.');
    const value=JSON.parse(raw);
    if(!value||typeof value.name!=='string'||!value.name.trim()||value.name.trim().length>120||/[\x00-\x1f]/.test(value.name)
      ||!Array.isArray(value.shapes)||!value.shapes.length||value.shapes.length>3000)throw Error('The incoming vinyl data is invalid.');
    await importFile(new File([JSON.stringify({shapes:value.shapes})],`${value.name.trim()}.json`,{type:'application/json'}));
    completedHandoffs.add(id);clearFragment();handoffMessage(t`${value.name.trim()} imported.`);
  } catch(error) {
    if(!disposed)handoffMessage(t`${errorText(error)} Retry, or use Add vinyl to import the JSON file.`,true,true);
  } finally {
    handoffWorking=false;
    if(!disposed){setBusy(false);if(window.location?.hash&&window.location.hash!==hash)void importHostVinyl();}
  }
}
async function exportSection() {
  const section=$('section').value;
  if(config.section_vinyl_export!==true||!project.placements.some(p=>p.section===section&&p.visible&&p.opacity>0))return;
  const status=$('sectionExportStatus');status.textContent=t`Exporting ${sectionLabel(section)}...`;status.classList.toggle('error',false);
  try {
    const validated=validateProject(project,config.vehicle,config.sections.map(s=>s.section));
    const response=await fetch('./api/export-section',{method:'POST',headers:{'Content-Type':'application/json'},body:serializeProject({project:validated,section}),signal:stop.signal});
    if(!response.ok)throw await responseError(response);
    if(response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!=='application/json')throw Error('The section export did not return native JSON. Nothing was downloaded.');
    const raw=await response.text();
    if(new TextEncoder().encode(raw).byteLength>8*1024*1024)throw Error('The section export exceeds the 8 MiB native vinyl limit. Nothing was downloaded.');
    let value;try{value=JSON.parse(raw);}catch{throw Error('The section export returned invalid JSON. Nothing was downloaded.');}
    const json=sectionVinylJson(value);
    if(disposed)return;
    const stem=`${config.vehicle.model_code}-${section}`.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').replace(/[. ]+$/g,'').slice(0,150)||'section';
    if(!await downloadBlob(new Blob([json],{type:'application/json'}),`${stem}.json`)){if(!disposed)status.textContent=t('Section export cancelled.');return;}
    if(disposed)return;
    status.textContent=t`${sectionLabel(section)}: ${value.shapes.length} native shapes exported.`;message(status.textContent);
  } catch(error) {
    if(!disposed){status.textContent=errorText(error);status.classList.toggle('error',true);$('sectionPanel').open=true;}
    throw error;
  }
}
async function openSaveArtwork() {
  if(config.experimental_export?.template_layout_available!==true)return;
  if(!await confirmReplace())return;
  experimentMessage('Opening save artwork...');
  try {
    const value=await api('template-layout');
    const file=new File([serializeProject(value)],`${config.vehicle.model_code}.kfps-layout.json`,{type:'application/json'});
    await openFile(file);
    experimentMessage('Save artwork opened. The source template was not changed.');
  } catch(error) {if(!disposed)experimentMessage(error.message,true);throw error;}
}
async function exportExperiment() {
  if(config.experimental_export?.enabled!==true||!project.placements.length)return;
  if(nonstockPreview()){experimentMessage(componentExportReason,true);return;}
  if(!await confirmExperiment())return;
  if(nonstockPreview()){experimentMessage(componentExportReason,true);return;}
  experimentMessage('Preparing experimental ZIP...');
  try {
    const value=validateProject(project,config.vehicle,config.sections.map(s=>s.section));
    const response=await fetch('./api/export-experiment',{method:'POST',headers:{'Content-Type':'application/json'},body:serializeProject(value),signal:stop.signal});
    if(!response.ok)throw await responseError(response);
    if(response.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!=='application/zip')throw Error('The server did not return an experimental ZIP. Nothing was downloaded.');
    const blob=await response.blob();
    if(!blob.size)throw Error('The experimental ZIP was empty. Nothing was downloaded.');
    if(disposed)return;
    if(!await downloadBlob(blob,`${config.vehicle.model_code}.livery-experiment.zip`)){if(!disposed)experimentMessage('Experimental ZIP export cancelled.');return;}
    if(disposed)return;
    experimentMessage('Experimental ZIP downloaded. Game acceptance is unverified; nothing was installed.');
  } catch(error) {if(!disposed)experimentMessage(error.message,true);throw error;}
}
function edit(callback) { if(editBlocked()||disposed||!flushNumeric())return; const before=snapshot(); callback(); commit(before); markAll(); }
function run(callback) { return async()=>{if(interactionBusy()||disposed||!flushNumeric())return; setBusy(true);try{await callback();}catch(error){if(!disposed)message(error.message,true);}finally{if(!disposed)setBusy(false);}}; }
function point(event) {const r=sectionCanvas.getBoundingClientRect();return [(event.clientX-r.left)*2048/r.width,(event.clientY-r.top)*1024/r.height];}
function hitPlacements(section,x,y) {
  const hits=[];
  for(let i=project.placements.length-1;i>=0;i--) {
    const p=project.placements[i];
    if(p.section!==section||!p.visible||p.opacity===0)continue;
    const bounds=artworkBounds(p.vinylId);if(!bounds)continue;
    // Pick the whole vinyl inside its transformed outline, including transparent gaps.
    const [u,v]=mapPoint(invertMatrix(placementMatrix(p)),x,y),px=u+1024,py=v+512;
    if(px>=bounds[0]&&px<=bounds[2]&&py>=bounds[1]&&py<=bounds[3])hits.push(p);
  }
  return hits;
}
function hitPlacement(section,x,y) { return hitPlacements(section,x,y)[0]?.id||null; }
function showPlacementStack(section,x,y) { const hits=hitPlacements(section,x,y);if(hits.length)tools?.showStack(hits);else message('No artwork under this pointer.'); }
function finishDrag(cancel=false) {
  if(!drag)return; const state=drag;drag=null;snapGuide=null;
  if(sectionCanvas.hasPointerCapture(state.id))sectionCanvas.releasePointerCapture(state.id);
  if(cancel)restore(state.before);else commit(state.before); markAll();
}
async function initialize() {
  config=await api('editor-config'); await sceneReady;
  if(!isSceneReady())throw Error('The car renderer could not start.');
  project=emptyProject(config.vehicle); saved=fingerprint();
  atlas.width=config.paint_size[0];atlas.height=config.paint_size[1];
  for(const section of config.sections)for(const id of ['section','placementSection']){const option=document.createElement('option');option.value=section.section;option.textContent=sectionLabel(section.section); $(id).append(option);}
  if(config.sections.some(s=>s.section==='Left'))$('section').value='Left';
  surface=createSurfaceEditor({canvas:$('canvas'),viewport:$('viewport'),config,
    getState:()=>({project,selected,aspectLocked:$('aspectLock').checked,busy:busy||saveWorking,dragging:!!drag||!!transform}),getBounds,hitPlacement,select:selectPlacement,
    begin:id=>beginTransform(id),preview:previewTransform,commit:()=>finishTransform(),cancel:()=>finishTransform(true),message,pickStack:showPlacementStack});
  confirmations=initializeActionConfirmations({message});
  tools=initializeStudioTools({action:studioAction,message,select:(id,options)=>selectPlacement(id,undefined,options),
    artworkButton:p=>artworkButton(project.vinyls.find(v=>v.id===p.vinylId),`${sectionLabel(p.section)}${locked(p.id)?' / Locked':''}`),
    state:()=>({project,selectedIds,busy:interactionBusy()||!canPreview(),locked:selectedIds.filter(locked),sourceEditing:sourceEdit,sourceEditorAvailable:config.source_editor_roundtrip===true})});
  inspection=initInspection({host:$('inspectionToolsHost'),message,isBusy:interactionBusy});
  if(config.project_storage?.enabled===true)projectStorage=initProjectStorage({api,message,
    defaultName:()=>config.vehicle.model_code,
    getDocumentRevision:()=>sourceDocumentId+':'+fingerprint(),
    onModalChange:()=>refresh(),
    getProject:()=>validateProject(project,config.vehicle,config.sections.map(s=>s.section)),
    loadProject:async(value,options)=>{setBusy(true);try{await openFile(new File([serializeProject(value)],'Saved.kfps-layout.json',{type:'application/json'}),options);}finally{if(!disposed)setBusy(false);}},
    importVinyl:async(file,options)=>{setBusy(true);try{await importFile(file,options);}finally{if(!disposed)setBusy(false);}},
    readVinyl:async entry=>{
      const response=await fetch(`./api/vinyl-library/file?path=${encodeURIComponent(entry.path)}`,{signal:stop.signal});
      if(!response.ok)throw await responseError(response);
      const blob=await response.blob();if(blob.size>8*1024*1024)throw Error('The vinyl JSON exceeds 8 MiB.');
      return new File([blob],entry.name,{type:'application/json'});
    },
    externalProject:options=>beginExternalPicker('project',options),externalVinyl:()=>beginExternalPicker('vinyl'),
  });
  if(config.recovery?.enabled===true)recovery=initRecovery({host:$('recoveryToolsHost'),api,getProject:()=>project,message,config,
    isBusy:()=>interactionBusy()||numericEdited.size>0,
    loadProject:async(value,{isCurrent})=>{await openFile(new File([serializeProject(value)],'Recovery.kfps-layout.json',{type:'application/json'}),{isCurrent,recovery:true});return true;}});
  surface.setMode(surfaceMode);
  for(const [mode,label] of Object.entries(modes))$('mode'+label).addEventListener('click',()=>setSurfaceMode(mode));
  $('aspectLock').addEventListener('change',()=>surface?.refresh());
  $('applyTransform').addEventListener('click',()=>{if(drag)finishDrag();else finishTransform();});
  $('cancelTransform').addEventListener('click',()=>{if(drag)finishDrag(true);else finishTransform(true);});
  $('showShortcuts').addEventListener('click',()=>{if(!interactionBusy())$('shortcuts').showModal();});
  $('section').addEventListener('change',()=>{if(interactionBusy())return;if(!flushNumeric()){if(current())$('section').value=current().section;return;}selected=null;refresh();schedule();});
  $('vinylSource').addEventListener('change',()=>{if(interactionBusy())return;pickedSource=$('vinylSource').value;refreshSources(false);});
  $('placeSource').addEventListener('click',placeSource);
  $('exportSource').addEventListener('click',run(exportSource));
  $('exportSection').addEventListener('click',run(exportSection));
  $('retryHostTransfer').addEventListener('click',()=>void importHostVinyl());
  window.addEventListener('hashchange',()=>void importHostVinyl(),{signal:stop.signal});
  $('placementSection').addEventListener('change',()=>{
    if(interactionBusy()||!current())return;
    if(!flushNumeric()){$('placementSection').value=current().section;return;}
    try {
      if(selectedIds.some(locked))throw Error('Unlock the selection before moving it to another section.');
      if(selectedIds.length>1||project.authoring?.groups?.some(group=>group.placements.includes(selected)))throw Error('Ungroup and select one placement before changing its section.');
      if(project.authoring?.links?.some(link=>link.a===selected||link.b===selected))throw Error('Unlink this pair before changing its section.');
      const next=movePlacementToSection(current(),$('placementSection').value,config.sections.map(s=>s.section));
      edit(()=>{Object.assign(current(),next);$('section').value=next.section;});
      message(t`Placement moved to ${sectionLabel(next.section)}.`);
    } catch(error) { refresh();message(error.message,true); }
  });
  $('importVinyl').addEventListener('click',()=>{if(!editBlocked()&&flushNumeric()){if(projectStorage&&config.vinyl_library?.enabled)projectStorage.addVinyl();else beginExternalPicker('vinyl');}});
  $('vinylFile').addEventListener('change',()=>completeExternalPicker('vinyl'));
  $('vinylFile').addEventListener('cancel',()=>completeExternalPicker('vinyl',true));
  $('openProject').addEventListener('click',async()=>{if(!interactionBusy()&&flushNumeric()&&await confirmReplace()){if(projectStorage)projectStorage.open();else beginExternalPicker('project');}});
  $('projectFile').addEventListener('change',()=>completeExternalPicker('project'));
  $('projectFile').addEventListener('cancel',()=>completeExternalPicker('project',true));
  $('saveProject').addEventListener('click',saveProject);
  $('chooseCar').addEventListener('click',()=>chooseCar());
  $('carSearch').addEventListener('input',()=>{if(!carWorking&&!carJob)renderCars();});
  $('switchCar').addEventListener('click',()=>switchCar());
  $('retryCarStatus').addEventListener('click',()=>switchCar(true));
  $('cancelCarSwitch').addEventListener('click',cancelCarSwitch);
  $('closeCarPicker').addEventListener('click',()=>{if(!carWorking)$('carPicker').close();});
  $('carPicker').addEventListener('cancel',event=>{event.preventDefault();cancelCarSwitch();});
  $('saveRecovery').addEventListener('click',saveProject);
  $('reloadPreview').addEventListener('click',()=>{if(disposed||interactionBusy())return;if(changed()){message('Save the layout before reloading the preview.',true);return;}window.location.reload();});
  $('openSaveArtwork').addEventListener('click',run(openSaveArtwork));
  $('exportExperiment').addEventListener('click',run(exportExperiment));
  $('resetParts').addEventListener('click',()=>{
    if(editBlocked()||disposed||!flushNumeric())return;
    const before=snapshot();retainParts(setVehicleParts({}));commit(before);
    message('Initial component configuration restored. Template tuning/body-kit data remain unchanged.');
  });
  $('undo').addEventListener('click',()=>{if(!editBlocked()&&flushNumeric())restoreHistory('undo');});$('redo').addEventListener('click',()=>{if(!editBlocked()&&flushNumeric())restoreHistory('redo');});
  for(const id of Object.keys(numeric))$(id).addEventListener('input',()=>{if(editBlocked()||disposed||!current())return;numericEdited.add(id);$('documentState').textContent=t('Unsaved layout');});
  for(const id of Object.keys(numeric))$(id).addEventListener('change',()=>commitNumeric(id));
  for(const [id,key] of Object.entries(numeric)) {
    const slider=$(id+'Range');
    slider.addEventListener('pointerdown',event=>{
      if(event.button===0&&!editBlocked())sliderPointer={field:id,id:event.pointerId,suppressed:false};
    });
    slider.addEventListener('input',()=>{
      if(sliderPointer?.field===id&&sliderPointer.suppressed){refreshTransformFields();return;}
      if(busy||saveWorking||drag||!current()||(transform&&(transform.kind!=='slider'||transform.field!==id)))return;
      const value=slider.valueAsNumber;
      if(!Number.isFinite(value))return;
      if(!transform&&!beginTransform(selected,'slider',id))return;
      try {
        let patch={[key]:value};
        if((key==='scaleX'||key==='scaleY')&&$('aspectLock').checked) {
          const base=transform.before.placements.find(p=>p.id===selected),next=scalePlacement(base,key,value,true);
          patch={scaleX:next.scaleX,scaleY:next.scaleY};
        }
        if(!previewTransform(selected,patch))refreshTransformFields();
      } catch(error){refreshTransformFields();message(error.message,true);}
    });
    slider.addEventListener('change',()=>{if(transform?.kind==='slider'&&transform.field===id)finishTransform();});
    slider.addEventListener('pointercancel',()=>{if(transform?.kind==='slider'&&transform.field===id)finishTransform(true);});
  }
  const releaseSlider=event=>{
    if(sliderPointer?.id!==event.pointerId)return;
    const field=sliderPointer.field;sliderPointer=null;
    if(transform?.kind==='slider'&&transform.field===field)finishTransform(event.type!=='pointerup');
  };
  for(const type of ['pointerup','pointercancel','lostpointercapture'])window.addEventListener(type,releaseSlider,{signal:stop.signal});
  $('visible').addEventListener('change',()=>{
    try{edit(()=>{
      if(selectedIds.some(locked))throw Error('Unlock the selection before changing visibility.');
      let next={...project,placements:project.placements.map(p=>selectedIds.includes(p.id)?{...p,visible:$('visible').checked}:p)};
      if(project.authoring?.links?.length)next=mirror.propagateLinks(project,next,selectedIds).project;
      project=next;
    });}catch(error){refresh();message(error.message,true);}
  });
  $('remove').addEventListener('click',()=>studioAction('remove').catch(error=>message(error.message,true)));
  $('duplicate').addEventListener('click',()=>studioAction('duplicate').catch(error=>message(error.message,true)));
  for(const [id,step] of [['forward',1],['backward',-1]])$(id).addEventListener('click',()=>{
    try{edit(()=>{
      if(selectedIds.some(locked))throw Error('Unlock the selection before reordering.');
      const ids=new Set(selectedIds),order=project.placements.filter(p=>ids.has(p.id));
      if(step>0)order.reverse();
      for(const p of order){
        const i=project.placements.findIndex(item=>item.id===p.id),j=placementStepIndex(project.placements,p.id,step);
        if(i>=0&&j>=0&&!ids.has(project.placements[j].id))[project.placements[i],project.placements[j]]=[project.placements[j],project.placements[i]];
      }
    });}catch(error){message(error.message,true);}
  });
  sectionCanvas.addEventListener('pointerdown',event=>{
    if(editBlocked()||event.button!==0||!flushNumeric())return;const position=point(event);
    if(event.altKey){event.preventDefault();showPlacementStack($('section').value,...position);return;}
    const id=hitPlacement($('section').value,...position),p=project.placements.find(item=>item.id===id);
    if(!selectPlacement(id,undefined,{additive:event.shiftKey})||!p||event.shiftKey||selectedIds.some(locked))return;
    event.preventDefault();sectionCanvas.focus({preventScroll:true});drag={id:event.pointerId,placementId:p.id,point:position,x:p.x,y:p.y,before:snapshot()};sectionCanvas.setPointerCapture(event.pointerId);refresh();
  });
  sectionCanvas.addEventListener('pointermove',event=>{if(!drag||drag.id!==event.pointerId)return;const [x,y]=point(event);
    try{project=transformProject(projectAt(drag.before),drag.placementId,{x:Math.max(-4096,Math.min(4096,drag.x+x-drag.point[0])),y:Math.max(-4096,Math.min(4096,drag.y-y+drag.point[1]))},{bypassSnap:event.ctrlKey});markAll();refreshTransformFields();}
    catch(error){message(error.message,true);}
  });
  sectionCanvas.addEventListener('pointerup',event=>{if(drag?.id===event.pointerId)finishDrag();});
  sectionCanvas.addEventListener('pointercancel',event=>{if(drag?.id===event.pointerId)finishDrag(true);});
  sectionCanvas.addEventListener('lostpointercapture',event=>{if(drag?.id===event.pointerId)finishDrag(true);});
  window.addEventListener('blur',()=>{finishDrag(true);finishTransform(true);});
  window.addEventListener('keydown',event=>{
    if(disposed||event.isComposing||event.keyCode===229||event.getModifierState('AltGraph')||event.target.closest('dialog,[contenteditable=true]'))return;
    const saveKey=(event.ctrlKey||event.metaKey)&&!event.altKey&&event.code==='KeyS';
    const numericField=Object.hasOwn(numeric,event.target.id);
    if(previewError&&saveKey&&(!event.target.closest('input,select,textarea')||numericField)){
      event.preventDefault();return saveProject();
    }
    if(previewError)return;
    const editorShortcut=(event.ctrlKey||event.metaKey)&&!event.altKey&&['KeyZ','KeyY','KeyS','KeyD'].includes(event.code);
    // Prevent native text undo/page actions while an editor transaction owns input.
    if((busy||saveWorking||transform||drag)&&editorShortcut){event.preventDefault();return;}
    if(busy||saveWorking||disposed||event.isComposing||event.getModifierState('AltGraph'))return;
    if(transform){if(event.key==='Escape'||event.key==='Enter'){event.preventDefault();finishTransform(event.key==='Escape');}return;}
    if(drag){if(event.key==='Escape'||event.key==='Enter'){event.preventDefault();finishDrag(event.key==='Escape');}return;}
    if(numericField){
      if(saveKey){event.preventDefault();if(commitNumeric(event.target.id))return saveProject();}
      else if(event.key==='Escape'&&!event.altKey&&!event.ctrlKey&&!event.metaKey){event.preventDefault();cancelNumeric(event.target.id);}
      return;
    }
    if(event.target.closest('input,select,textarea,dialog,[contenteditable=true]'))return;
    if((event.ctrlKey||event.metaKey)&&!event.altKey){
      if(event.code==='KeyZ'){event.preventDefault();if(flushNumeric())restoreHistory(event.shiftKey?'redo':'undo');}
      else if(event.code==='KeyY'){event.preventDefault();if(flushNumeric())restoreHistory('redo');}
      else if(event.code==='KeyS'){event.preventDefault();return saveProject();}
      else if(event.code==='KeyD'&&current()){event.preventDefault();$('duplicate').click();}
      else if(event.code==='KeyA'){event.preventDefault();void studioAction('selectSection');}
      else if(event.code==='KeyG'){event.preventDefault();void studioAction(event.shiftKey?'ungroup':'group','Group').catch(error=>message(error.message,true));}
      return;
    }
    if(event.altKey||event.ctrlKey||event.metaKey)return;
    const mode={KeyO:'orbit',KeyV:'move',KeyS:'scale',KeyR:'rotate',KeyK:'skew'}[event.code];
    if(mode){event.preventDefault();setSurfaceMode(mode);return;}
    if(event.target!==sectionCanvas&&event.target!==$('canvas'))return;
    if(!current())return;
    if(event.key==='Delete'){event.preventDefault();$('remove').click();return;}
    const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,1],ArrowDown:[0,-1]}[event.key];
    if(delta){event.preventDefault();try{edit(()=>{const p=current(),n=event.shiftKey?10:1;project=transformProject(project,p.id,{x:Math.max(-4096,Math.min(4096,p.x+delta[0]*n)),y:Math.max(-4096,Math.min(4096,p.y+delta[1]*n))},{bypassSnap:true});});}catch(error){message(error.message,true);}}
  });
  window.addEventListener('beforeunload',event=>{if(!navigationAuthorized&&(changed()||saveWorking)){event.preventDefault();event.returnValue='';}});
  markAll();refresh();message('Ready.');await importHostVinyl();if(disposed)return;
  window.__liveryLab={getProject:()=>structuredClone(project),getSelection:()=>[...selectedIds],getMetrics:()=>({...metrics,cachedSources:images.size}),getScene:sceneState,getAtlas:()=>atlas.toDataURL(),ready:true};
  diagnostics.emit('readiness',{ready:true,...projectCounts(project,config.sections.length)});diagnostics.sample(true);
}
function componentSelectionChanged(){
  if(disposed||!project||!canPreview())return;
  const before=snapshot();retainParts(currentVehicleParts());commit(before);
  message('Component configuration changed. Saved with the layout; game export does not encode these choices.');
}
function viewerFailed(event) {
  if(disposed||previewError)return;
  previewError=typeof event.detail?.message==='string'?event.detail.message.slice(0,1024):'The car preview is unavailable.';
  if(!previewError.trim())previewError='The car preview is unavailable.';
  // Generic renderer failures arrive before scene disposal; stop pending work now.
  if(queued)cancelAnimationFrame(queued);queued=0;
  surface?.dispose();surface=null;
  if(project){finishDrag(true);finishTransform(true);}
  dirtySections.clear();
  for(const id of ['confirmOpen','confirmExperiment','confirmCarSwitch','shortcuts'])if($(id).open)$(id).close('cancel');
  $('previewRecovery').hidden=false;
  $('previewRecoveryMessage').textContent=t`${errorText(previewError)} Your layout is retained. Save it, reload the preview, then reopen the saved layout.`;
  refresh();message('Preview stopped. Save the retained layout before reloading.',true);
}
window.addEventListener('kfps-viewer-error',viewerFailed,{signal:stop.signal});
window.addEventListener('kfps-component-selection',componentSelectionChanged);
window.addEventListener('kfps-theme-applied',()=>{if(project&&!disposed&&canPreview())drawSelection();},{signal:stop.signal});
window.addEventListener('pagehide',()=>{disposed=true;projectStorage?.dispose();confirmations?.dispose();for(const url of nativeDownloads.keys())nativeDownloadFinished(url,{status:'cancelled'});surface?.dispose();surface=null;tools?.dispose();inspection?.dispose();window.removeEventListener('kfps-component-selection',componentSelectionChanged);stop.abort();if(queued)cancelAnimationFrame(queued);queued=0;for(const image of images.values())image.src='';images.clear();sources.clear();sourceButtons.clear();placementButtons.clear();sectionCanvases.clear();atlas.width=atlas.height=1;
  // Recovery's own unload handler runs after this listener. Retain the gesture
  // busy state until then so an unfinished transform cannot be auto-saved.
  queueMicrotask(()=>{recovery?.dispose();transform=null;drag=null;});
});
initialize().catch(error=>{message(error.message,true);$('importVinyl').disabled=true;});
