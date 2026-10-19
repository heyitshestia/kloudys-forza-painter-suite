"use strict";
// CPU-only protocol audit. Graphics acceptance and transport are controlled;
// recovery, project loading/saving and receipt ownership execute real source.
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm"), crypto = require("node:crypto");
const root = process.env.KFPS_TEST_APP_ROOT || path.resolve(__dirname,"../../..");
const web = path.join(root,"KFPS.Editor/web");
const source = fs.readFileSync(path.join(web,"editor.js"),"utf8");
const projectsPath = path.join(web,"editor-projects.js");
const {create} = require(projectsPath);
const sha = value => crypto.createHash("sha256").update(value).digest("hex");
const clone = value => JSON.parse(JSON.stringify(value));
const name = "Customization IME fixture";
const initial = {format:"kloudy_fabric_editor_project_v1",name,shapes:[{type:1048677,data:[0,0,.4,.4,0,0,0],color:[11,22,33,255]}]};
const deferred = () => {let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick = () => new Promise(resolve=>setImmediate(resolve));
function extract(name) {
  const match = new RegExp(`^(?:async )?function ${name}\\(`,"m").exec(source);
  assert.ok(match,`Actual source function missing: ${name}`);
  const end = source.indexOf("\n}",match.index);
  assert.ok(end>match.index);
  return source.slice(match.index,end+2);
}
const names = ["isDocumentDirty","confirmWorkspaceReplacement","recoverAutosavePayload","loadSelectedProject","loadProjectPayload","saveProject"];
const functions = names.map(extract).join("\n");
function world({verify=true,reference=true,saveMode="normal",exists=true,readFails=false}={}) {
  let disk=clone(initial), diskExists=exists, requests=0, history=0;
  const calls=[], errors=[], statuses=[], autosaves=[], prompts=[];
  const verifyGate=deferred(), saveGate=deferred(), readGate=deferred();
  const confirmation=deferred();
  const elements = new Map();
  const receipt = () => ({target_id:name+".fabric-project.json",fingerprint:sha(JSON.stringify(disk)),bytes:Buffer.byteLength(JSON.stringify(disk)),write_stage:"read"});
  const nodes = id => {
    if(!elements.has(id))elements.set(id,{disabled:false,open:id==="projectBrowserDialog",close(){this.open=false;}});
    return elements.get(id);
  };
  const c={
    console, structuredClone, documentGeneration:0,documentIdentity:0,recoveryRestoreDepth:0,
    currentProjectName:name,loadedName:name,documentDirty:true,projectSaveInProgress:false,
    overlayRevision:0,savedOverlayRevision:0,savedHistoryState:null,nudgeHistoryPending:false,
    history:{revision:0},shapes:clone(initial.shapes),editorCommands:{busy:false},
    projectBrowserState:{source:"projects",loading:false},PROJECT_FILE_API:"/project",
    KfpsI18n:{t:value=>value,error:value=>value},$:nodes,
    hasEditableWorkspace:()=>!!c.currentProjectName||c.shapes.length>0,
    currentHistoryState:()=>c.history,
    cleanProjectBaseName:(value,fallback)=>value||fallback,
    beginDocumentLoad:()=>++c.documentGeneration,
    setBusy:()=>{c.editorCommands.busy=true;},clearBusy:()=>{c.editorCommands.busy=false;},
    setStatus:value=>statuses.push(value),setProjectBrowserStatus:value=>statuses.push(value),
    nextFrame:async()=>{},flushPendingNudgeHistory:()=>{},ensureHistoryBaseline:()=>{},
    presentAcceptedDocument:callback=>callback(),renderHistoryList:()=>{},showCornerNotice:()=>{},
    showError:(title,error)=>errors.push({title,message:String(error?.message||error)}),
    updateDocumentState:()=>{c.documentDirty=c.isDocumentDirty();},
    snapshotEditorState:()=>c.history,autosavePayloadFromState:state=>({state,documentIdentity:c.documentIdentity}),
    writeAutosavePayload:payload=>autosaves.push(payload),
    selectedProjectEntry:()=>({id:name+".fabric-project.json",title:name}),
    requestConfirmation:async(...args)=>{prompts.push(args);return confirmation.promise;},
    requestTextInput:async()=>c.promptName,
    promptName:name,
    editableProjectPayload:projectName=>({format:initial.format,name:projectName,shapes:clone(c.shapes)}),
    autosaveSummary:()=>name,
  };
  const transport={request:async(operation,data)=>{
    calls.push({operation,data:clone(data)});
    if(operation==="fetchJSON") {
      if(data.url.includes("request_id=")) {
        if(saveMode==="lost")return c.committed;
        return {status:"unknown"};
      }
      if(verify==="deferred")return verifyGate.promise;
      if(verify==="reject")throw Error("receipt unavailable");
      return {current:verify};
    }
    assert.equal(operation,"saveProject");
    if(diskExists&&!data.overwrite)throw Object.assign(Error("exists"),{code:"project_exists"});
    if(diskExists&&data.expected_fingerprint!==receipt().fingerprint)throw Object.assign(Error("conflict"),{code:"project_conflict"});
    if(saveMode==="deferred")await saveGate.promise;
    if(saveMode==="failure")throw Error("transport failed");
    disk=clone(data.payload);diskExists=true;
    const result={status:"committed",title:data.name,receipt:{...receipt(),request_id:data.request_id,write_stage:"committed"}};
    c.committed=result;
    if(saveMode==="lost")throw Error("reply lost after commit");
    return result;
  }};
  c.editorProjects=create({persistence:transport,generation:()=>c.documentIdentity,requestId:()=>String(++requests).padStart(32,"0")});
  c.saveProjectToAppFolder=(...args)=>c.editorProjects.save(...args);
  c.editorReference={
    restoreSourceOverlayFromProject:async()=>{if(reference==="error")throw Error("reference unavailable");return reference;},
    clearSourceOverlayState:()=>{},preserveUnavailable:()=>{},
  };
  c.loadPayload=async(payload,options={})=>{
    if(options.generation!==undefined&&options.generation!==c.documentGeneration)return false;
    c.documentIdentity++;c.history={revision:++history};c.shapes=clone(payload.shapes);
    c.currentProjectName=options.projectName??c.currentProjectName;
    c.savedHistoryState=null;c.overlayRevision=0;c.savedOverlayRevision=0;c.nudgeHistoryPending=false;
    c.editorProjects.associate(options.receipt,c.currentProjectName);
    c.documentDirty=c.isDocumentDirty();c.recoveryRestoreDepth=0;c.editorCommands.busy=false;
    return true;
  };
  c.readEditorDocument=async()=>{
    if(readFails===true)throw Error("read failed");
    if(readFails==="deferred")await readGate.promise;
    return {payload:clone(disk),receipt:receipt()};
  };
  const sandbox=vm.createContext(c);
  vm.runInContext(functions,sandbox);
  const payload=(saved=true,validReceipt=true)=>({...clone(initial),editor_session:{project_name:name,saved,receipt:validReceipt?receipt():null}});
  const recover=async(p=payload())=>{c.recoveryAutosavePayload=p;return c.recoverAutosavePayload(p);};
  const edit=()=>{c.shapes[0].data[0]+=.25;c.history={revision:++history};c.documentDirty=c.isDocumentDirty();};
  const load=()=>c.loadProjectPayload(clone(disk),name,{receipt:receipt()});
  return {c,calls,errors,statuses,autosaves,prompts,verifyGate,saveGate,readGate,confirmation,payload,recover,edit,load,
    disk:()=>clone(disk),receipt,externalEdit:()=>{disk.shapes[0].data[0]+=7;}};
}
const cases=[];
async function check(label,fn){await fn();cases.push(label);}
(async()=>{
  await check("reproduce premature idle and stale dirty prediction using actual recovery and picker functions",async()=>{
    const w=world({verify:"deferred"}), pending=w.recover();await tick();
    assert.equal(w.c.recoveryRestoreDepth,0);assert.equal(w.c.editorCommands.busy,false);
    assert.equal(w.c.documentDirty,true);assert.equal(w.c.savedHistoryState,null);
    assert.ok(w.c.recoveryAutosavePayload,"Old fixture considers this unfinished recovery ready");
    const predictedConfirmation=w.c.documentDirty;
    w.verifyGate.resolve({current:true});assert.equal(await pending,true);
    assert.equal(w.c.documentDirty,false);assert.equal(w.c.recoveryAutosavePayload,null);
    await w.c.loadSelectedProject();assert.equal(w.prompts.length,0);
    assert.equal(predictedConfirmation,true);assert.equal(w.c.documentDirty,false);
  });
  for(const saved of [true,false])for(const validReceipt of [true,false])for(const verify of [true,false,"reject"]){
    await check(`recovery saved=${saved} receipt=${validReceipt} verify=${verify}`,async()=>{
      const w=world({verify});assert.equal(await w.recover(w.payload(saved,validReceipt)),true);
      assert.equal(w.c.documentDirty,!(saved&&validReceipt&&verify===true));
      assert.equal(w.c.recoveryAutosavePayload,null);
      assert.equal(!!w.c.editorProjects.expected(name),validReceipt&&verify===true);
    });
  }
  for(const reference of [false,"error"]){
    await check(`recovery cannot mark clean with reference=${reference}`,async()=>{
      const w=world({reference});await w.recover();assert.equal(w.c.documentDirty,true);
      assert.equal(w.c.recoveryAutosavePayload,null);
    });
  }
  for(const mutation of ["history","overlay","nudge","document"]){
    await check(`pending receipt verification preserves newer ${mutation}`,async()=>{
      const w=world({verify:"deferred"}),pending=w.recover();await tick();
      if(mutation==="history")w.edit();
      if(mutation==="overlay")w.c.overlayRevision++;
      if(mutation==="nudge")w.c.nudgeHistoryPending=true;
      if(mutation==="document")await w.c.loadPayload({shapes:[]},{projectName:"Other"});
      w.verifyGate.resolve({current:true});const result=await pending;
      assert.equal(result,mutation!=="document");
      assert.equal(w.c.isDocumentDirty(),true);
      if(mutation==="document")assert.equal(w.c.editorProjects.association,null);
    });
  }
  for(const accept of [false,true]){
    await check(`dirty picker confirmation accept=${accept}`,async()=>{
      const w=world({verify:false});await w.recover();const identity=w.c.documentIdentity;
      const pending=w.c.loadSelectedProject();await tick();assert.equal(w.prompts.length,1);
      assert.equal(w.c.documentIdentity,identity);
      w.confirmation.resolve(accept);await pending;
      assert.equal(w.c.documentIdentity>identity,accept);assert.equal(w.c.documentDirty,!accept);
      assert.equal(!!w.c.editorProjects.expected(name),accept);
    });
  }
  await check("failed picker read preserves current dirty work",async()=>{
    const w=world({verify:false,readFails:true});await w.recover();const id=w.c.documentIdentity;
    w.confirmation.resolve(true);await w.c.loadSelectedProject();assert.equal(w.c.documentIdentity,id);
    assert.equal(w.c.documentDirty,true);assert.equal(w.errors.length,1);
  });
  await check("stale picker response does not replace newer document",async()=>{
    const w=world({readFails:"deferred"});await w.recover();const pending=w.c.loadSelectedProject();await tick();
    ++w.c.documentGeneration;await w.c.loadPayload({shapes:[]},{projectName:"Other"});
    w.readGate.resolve();await pending;assert.equal(w.c.currentProjectName,"Other");
  });
  await check("picker read receipt enables ordinary save and independent reopen",async()=>{
    const w=world();await w.load();const old=w.receipt().fingerprint;w.edit();
    await w.c.saveProject();const write=w.calls.find(x=>x.operation==="saveProject");
    assert.equal(write.data.overwrite,true);assert.equal(write.data.expected_fingerprint,old);
    assert.equal(w.c.documentDirty,false);assert.equal(w.disk().shapes[0].data[0],.25);
    await w.load();assert.deepEqual(w.c.shapes,w.disk().shapes);assert.equal(w.c.documentDirty,false);
  });
  for(const mode of ["saveAs","noReceipt","conflict","failure","lost"]){
    await check(`save boundary ${mode}`,async()=>{
      const w=world({saveMode:mode==="failure"||mode==="lost"?mode:"normal"});await w.load();w.edit();
      if(mode==="noReceipt")w.c.editorProjects.associate(null,name);
      if(mode==="conflict")w.externalEdit();
      const before=w.disk();await w.c.saveProject({saveAs:mode==="saveAs"});
      assert.equal(w.c.projectSaveInProgress,false);
      assert.equal(w.c.documentDirty,mode!=="lost");
      assert.equal(w.calls.filter(x=>x.operation==="saveProject").length,1,"No write replay");
      if(mode!=="lost"){assert.deepEqual(w.disk(),before);assert.equal(w.errors.length,1);}
      else {assert.equal(w.c.editorProjects.expected(name).fingerprint,w.receipt().fingerprint);assert.equal(w.errors.length,0);}
    });
  }
  await check("cancelled Save As never writes or marks clean",async()=>{
    const w=world();await w.load();w.edit();w.c.promptName=null;await w.c.saveProject({saveAs:true});
    assert.equal(w.calls.length,0);assert.equal(w.c.documentDirty,true);assert.equal(w.c.projectSaveInProgress,false);
  });
  for(const change of ["history","document"]){
    await check(`inflight save preserves newer ${change}`,async()=>{
      const w=world({saveMode:"deferred"});await w.load();w.edit();const pending=w.c.saveProject();await tick();
      if(change==="history")w.edit();else {++w.c.documentGeneration;await w.c.loadPayload({shapes:[]},{projectName:"Other"});}
      w.saveGate.resolve();await pending;assert.equal(w.c.documentDirty,true);
      if(change==="history")assert.equal(w.c.shapes[0].data[0],.5);
      else {assert.equal(w.c.currentProjectName,"Other");assert.equal(w.c.editorProjects.association,null);}
      assert.equal(w.disk().shapes[0].data[0],.25);
    });
  }
  console.log(JSON.stringify({passed:true,cases:cases.length,caseNames:cases,sourceRoot:root,
    editorSha256:sha(source),projectsSha256:sha(fs.readFileSync(projectsPath)),
    actualFunctions:names,controlledBoundaries:["Fabric geometry acceptance","reference image I/O","persistence transport","user confirmation"],
    browserLaunches:0,filesystemWrites:0},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
