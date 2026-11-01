import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as monitor from '../../tools/livery-studio/src/web/source-edit-monitor.mjs';
import {t,setLanguage,errorText} from '../../tools/livery-studio/src/web/i18n.mjs';

const source=readFileSync(new URL('../../tools/livery-studio/src/web/livery-editor.mjs',import.meta.url),'utf8');
function between(text,start,end){
  const first=text.indexOf(start),last=text.indexOf(end,first+start.length);
  assert.ok(first>=0&&last>first,`Product function moved: ${start}`);
  return text.slice(first,last);
}
function harness(){
  const messages=[],requests=[];
  const job={id:'job',documentId:'document',sourceId:'source',sourceRevision:0,
    vinylId:'vinyl',placementId:'placement',name:'<img src=x> {0}',status:'ready'};
  const context=vm.createContext({
    ...monitor,t,errorText,sourceEdit:job,sourceDocumentId:'document',disposed:false,
    sourceMonitor:{stop(){},start(){}},crypto:{randomUUID:()=> 'replacement'},
    project:{vinyls:[{id:'vinyl',name:job.name,shapes:[]}],placements:[{id:'placement',vinylId:'vinyl'}]},
    selectedIds:['placement'],selected:'placement',editBlocked:()=>false,flushNumeric:()=>true,
    locked:()=>false,diagnostics:{emit(){}},confirmOperation:async()=>true,confirmationSpec:()=>({}),
    setBusy(){},syncSourceLinks:(_,next)=>next,applyProjectChange:async()=>{},
    tools:{status:(_,text)=>messages.push(text),refresh(){}},
    api:async(path)=>{requests.push(path);return {source:{shapes:[]}};},
  });
  vm.runInContext(between(source,'function sourceEditMessage(','function finishTransform('),context);
  return {context,job,messages,requests};
}

test('all remote and local presentation states have EN/KO/JA messages',()=>{
  assert.equal(typeof monitor.sourceEditStatusKey,'function');
  const keys=JSON.parse(readFileSync(new URL('../../tools/livery-studio/src/web/locales/messages.json',import.meta.url),'utf8'));
  for(const status of ['launching','editing','ready','taken','cancelled','failed','expired','stale','applying','applied','apply-failed']){
    const key=monitor.sourceEditStatusKey(status);
    assert.ok(key&&keys[key],status);
    for(const language of ['en','ko','ja']){
      setLanguage(language);
      assert.equal(t(key),language==='en'?key:keys[key][language==='ko'?0:1]);
      if(language!=='en')assert.notEqual(t(key),key);
    }
  }
  setLanguage('en');
  assert.notEqual(monitor.sourceEditStatusKey('taken'),monitor.sourceEditStatusKey('applied'));
});

test('apply shows destination, applying then applied only after local replacement',async()=>{
  const {context,job,messages}=harness();let finish;
  context.applyProjectChange=()=>new Promise(resolve=>finish=resolve);
  const pending=context.studioAction('applySourceEdit','selection');
  await new Promise(resolve=>setImmediate(resolve));
  assert.ok(messages.at(-1).includes('Applying'),messages.at(-1));
  assert.ok(messages.at(-1).includes(job.name),'Name stays opaque text');
  assert.ok(messages.at(-1).includes('Studio'),'Destination is visible');
  assert.equal(context.sourceEdit,job);
  finish();await pending;
  assert.ok(messages.at(-1).includes('Applied'),messages.at(-1));
  assert.equal(context.sourceEdit,null);
});

test('take or local apply failure stays visible and never reports applied',async()=>{
  for(const boundary of ['api','applyProjectChange']){
    const {context,job,messages}=harness();
    context[boundary]=async()=>{throw Error('Test failure');};
    await assert.rejects(context.studioAction('applySourceEdit','all'),/Test failure/);
    assert.equal(context.sourceEdit,job);
    assert.ok(messages.at(-1).includes('Could not apply'),messages.at(-1));
    assert.ok(messages.at(-1).includes('Test failure'));
    assert.ok(!messages.some(text=>text.includes('Applied.')));
  }
});

test('cancelled or replaced job cannot publish late apply status',async()=>{
  const {context,job,messages}=harness();let finish;
  context.api=()=>new Promise(resolve=>finish=resolve);
  const pending=context.studioAction('applySourceEdit','all');
  await new Promise(resolve=>setImmediate(resolve));
  context.sourceEdit={id:'new-job'};
  finish({source:{shapes:[]}});
  await assert.rejects(pending,/interrupted/);
  assert.equal(messages.length,1,'Old job must not overwrite current status');
  assert.notEqual(context.sourceEdit,job);
});

test('a pending poll is discarded when explicit apply starts',async()=>{
  const {context,job,messages}=harness();let finishPoll,finishApply;
  context.sourceMonitor=monitor.createSourceEditMonitor({read:()=>new Promise(resolve=>finishPoll=resolve),
    update:(_,value)=>messages.push(value.status),schedule:()=>0,cancel(){}});
  context.sourceMonitor.start(job);
  const poll=context.sourceMonitor.check();
  context.applyProjectChange=()=>new Promise(resolve=>finishApply=resolve);
  const apply=context.studioAction('applySourceEdit','all');
  await new Promise(resolve=>setImmediate(resolve));
  finishPoll({status:'ready'});await poll;
  assert.ok(!messages.includes('ready'));
  finishApply();await apply;
});

test('manual checks retain apply failure until a terminal job status supersedes it',async()=>{
  const {context,job,messages}=harness();
  context.createSourceEditMonitor=options=>monitor.createSourceEditMonitor({...options,schedule:()=>0,cancel(){}});
  vm.runInContext(between(source,'const sourceMonitor=createSourceEditMonitor(','let sourceDocumentId=')
    +'globalThis.testMonitor=sourceMonitor;',context);
  context.api=async()=>{throw Error('Apply test failure');};
  await assert.rejects(context.studioAction('applySourceEdit','all'),/Apply test failure/);
  context.api=async()=>({status:'taken'});
  await context.testMonitor.check();
  assert.equal(job.status,'taken');
  assert.ok(messages.at(-1).includes('Could not apply returned artwork.'));
  assert.ok(messages.at(-1).includes('Apply test failure'));
  context.api=async()=>({status:'stale'});
  await context.testMonitor.check();
  assert.equal(job.status,'stale');
  assert.ok(messages.at(-1).includes('out of date'));
  assert.ok(!messages.at(-1).includes('Apply test failure'));
  context.testMonitor.stop();
});

test('remote cancelled, stale and expired jobs stop automatic checks without applying',async()=>{
  for(const status of ['cancelled','stale','expired']){
    const tasks=new Map(),job={id:'job',status:'editing'};
    const observer=monitor.createSourceEditMonitor({read:async()=>({status}),
      update:(target,value)=>{target.status=value.status;},
      schedule:callback=>{tasks.set(1,callback);return 1;},cancel:id=>tasks.delete(id)});
    observer.start(job);await observer.check();
    assert.equal(job.status,status);assert.equal(tasks.size,0);
    observer.stop();
  }
});

test('Editor destination and return states render names as text, not markup',()=>{
  const adapter=readFileSync(new URL('../../KFPS.Editor/web/editor-workspace.js',import.meta.url),'utf8');
  const node={textContent:'',hidden:false,dataset:{}};
  const context=vm.createContext({$:()=>node,document:{querySelector:()=>null},t:(key,...values)=>key.replace(/\{(\d+)\}/g,(_,i)=>values[i])});
  vm.runInContext(between(adapter,'  function refreshSourceStatus(','  function setupTools('),context);
  const source={name:'<svg onload=bad()> {0}'};
  for(const [state,expected] of [['editing','Editing'],['returning','Returning'],['returned','Returned'],['changed','Changes not returned'],['failed','Could not return'],['stale','different document']]){
    context.refreshSourceStatus(source,state);
    assert.ok(node.textContent.includes(source.name));
    assert.ok(node.textContent.includes('Destination: Livery Studio'));
    assert.ok(node.textContent.includes(expected),node.textContent);
    assert.equal(node.hidden,false);
    assert.equal(node.innerHTML,undefined);
  }
  context.refreshSourceStatus(null);
  assert.equal(node.hidden,true,'Ordinary Editor has no source destination');
});

test('Editor return command publishes progress, success, failure and document mismatch',async()=>{
  const editor=readFileSync(new URL('../../KFPS.Editor/web/editor.js',import.meta.url),'utf8');
  const calls=[],button={classList:{toggle(){}}},returnedHistory={};
  let history=returnedHistory;
  const context=vm.createContext({
    window:{KfpsWorkspace:{refreshSourceStatus:(source,state)=>calls.push([source,state])}},
    $:()=>button,documentIdentity:1,EDITOR_MUTATION_HEADERS:{},
    KfpsI18n:{t:value=>value},flushPendingNudgeHistory(){},vinylObjects:()=>[{}],
    refreshExportValidation:()=>({errors:[]}),objectToShape:()=>({}),setStatus(){},showError(){},
    currentHistoryState:()=>history,nudgeHistoryPending:false,document:{},
    hasEditableWorkspace:()=>true,isDocumentDirty:()=>false,currentProjectName:'fixture',loadedName:'fixture',
    cleanProjectBaseName:value=>value,setText(){},
    fetch:async()=>({ok:true,json:async()=>({message:'Returned'})}),
  });
  vm.runInContext(between(editor,'let studioSourceContext = null;','async function openLiveryStudio('),context);
  vm.runInContext(between(editor,'function updateDocumentState()','function markCurrentHistorySaved('),context);
  vm.runInContext('studioSourceContext={name:"Body",generation:1,jobId:"job",projectId:"source"}',context);
  await context.returnLiverySource();
  assert.deepEqual(calls.map(value=>value[1]),['returning','returned']);
  assert.equal(button.disabled,false);
  history={};
  context.updateDocumentState();
  assert.equal(calls.at(-1)[1],'changed','Editing after return is not reported as returned');
  history=returnedHistory;
  context.updateDocumentState();
  assert.equal(calls.at(-1)[1],'returned','Undo to the returned snapshot restores returned state');
  context.nudgeHistoryPending=true;
  context.updateDocumentState();
  assert.equal(calls.at(-1)[1],'changed','Pending edits cannot display returned state');
  context.nudgeHistoryPending=false;
  calls.length=0;
  context.fetch=async()=>({ok:false,json:async()=>({error:'Expired'})});
  await context.returnLiverySource();
  assert.deepEqual(calls.map(value=>value[1]),['returning','failed']);
  context.documentIdentity=2;
  context.updateDocumentState();
  assert.equal(calls.at(-1)[1],'stale');
  assert.equal(button.disabled,true);
  assert.match(between(editor,'  documentIdentity++;','function removeVinylObjectHelpers('),/updateDocumentState/,
    'Accepted document loads must retain the existing status refresh hook');
});

test('status catalogs and generated packs agree and preserve opaque placeholders',()=>{
  const root=new URL('../../',import.meta.url);
  const keys=['Source artwork: {0}','Close {0}','Source: {0} | Destination: Livery Studio',
    'Editing source artwork.','Returning source artwork...','Returned to Studio.',
    'Changes not returned. Start a new source edit in Studio.'];
  for(const language of ['en','ko','ja']){
    const catalog=JSON.parse(readFileSync(new URL(`KFPS.Editor/web/locales/${language}.json`,root),'utf8'));
    const pack={window:{}};
    vm.runInNewContext(readFileSync(new URL(`KFPS.Editor/web/locales/${language}.js`,root),'utf8'),pack);
    for(const key of keys){
      assert.ok(catalog.messages[key],`${language}: ${key}`);
      assert.equal(pack.window.KfpsEditorLocales[language].messages[key],catalog.messages[key]);
      assert.deepEqual(catalog.messages[key].match(/\{\d+\}/g),key.match(/\{\d+\}/g));
    }
  }
});
