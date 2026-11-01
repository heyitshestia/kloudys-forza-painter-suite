// Real web pages and car assets; deterministic in-memory API fixtures, no game writes.
const {chromium}=require('playwright');
const {PNG}=require(require('node:path').join(require.resolve('playwright-core/package.json'),'../lib/utilsBundle.js'));
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../../..');
assert(process.env.KFPS_TEST_OUTPUT && process.env.KFPS_TEST_CAR_ROOT,
  'Set KFPS_TEST_OUTPUT to an isolated evidence directory and KFPS_TEST_CAR_ROOT to prepared local test assets.');
const run=path.resolve(process.env.KFPS_TEST_OUTPUT),car=path.resolve(process.env.KFPS_TEST_CAR_ROOT);
const prepared=JSON.parse(fs.readFileSync(path.join(car,'prepared.json')));
const studioProjectId='b'.repeat(32);
const switchedToken='d'.repeat(43),switchJobId='e'.repeat(32),otherCar={car_id:3762,model_code:'FIXTURE_OTHER_CAR'};
const calls=[],missing=[],savedProjects=new Map();let lastExport=null,lastProject=null,studioSaved=null,sectionFailure=false,releaseRestore=null,holdCarPreparation=false,releaseCommit=null;
fs.mkdirSync(run,{recursive:true});
const shape={type:1048677,data:[0,0,1,1,0,0,0],color:[20,160,210,255],editor_group_id:'g',editor_group_name:'Group',editor_group_path:[{id:'outer',name:'Outer'},{id:'g',name:'Group'}]};
const png=new PNG({width:2048,height:1024});
for(let y=400;y<600;y++)for(let x=800;x<1200;x++){const i=(y*2048+x)*4;png.data[i]=20;png.data[i+1]=160;png.data[i+2]=210;png.data[i+3]=255;}
const preview='data:image/png;base64,'+PNG.sync.write(png).toString('base64');
const config={...prepared.editor_config,project_storage:{enabled:true},source_editor_roundtrip:true,section_vinyl_export:true,experimental_export:{enabled:true,template_layout_available:false},recovery:{enabled:true,debounce_ms:10000},car_switch:true};
const mime={'.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.png':'image/png','.svg':'image/svg+xml','.woff2':'font/woff2','.glb':'model/gltf-binary'};
function file(res,name){if(!fs.existsSync(name)){missing.push(name);res.writeHead(404);res.end();return;}const data=fs.readFileSync(name);res.writeHead(200,{'Content-Type':mime[path.extname(name)]||'application/octet-stream','Content-Length':data.length});res.end(data);}
const server=http.createServer(async(req,res)=>{
  const url=new URL(req.url,'http://localhost'),p=decodeURIComponent(url.pathname);let body='';for await(const chunk of req)body+=chunk;
  let value;try{value=body?JSON.parse(body):null;}catch{}
  const json=(data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  if(p.includes('/api/'))calls.push({path:p,method:req.method});
  if(p.startsWith('/api/fabric-editor/')){
    const action=p.split('/').pop();
    if(action==='preferences')return json({ok:true,settings:{kloudyFabricLanguage:'en',kloudyFabricProjectSharingAcknowledged:'1',kloudyFabricLanguageNoticeAcknowledged:'1',kloudyFabricEditorUpdateAcknowledged:'modernization-1'}});
    if(action==='startup-help-confirmed')return json({confirmed:true});
    if(action==='themes')return json({themes:[]});
    if(action==='json-browser')return json({groups:[],source:'editor'});
    if(action==='project-browser')return json({entries:[],folder:'Fixture projects'});
    if(action==='autosave')return json({ok:true,found:false,candidates:[],history:[]});
    if(action==='save-editor-json'||action==='save-project'){
      const exporting=action==='save-editor-json',name=value.name+(exporting?'.fh6-import.json':'.fabric-project.json');
      if(exporting)lastExport=value.payload;else{lastProject=value.payload;savedProjects.set(name,value.payload);}
      const data=JSON.stringify(value.payload),receipt={request_id:value.request_id,target_id:name,fingerprint:crypto.createHash('sha256').update(data).digest('hex'),bytes:Buffer.byteLength(data),write_stage:'committed'};
      fs.writeFileSync(path.join(run,name),data);return json({receipt,name,id:name,title:value.name,path:path.join(run,name)});
    }
    if(action==='project-file')return json({payload:savedProjects.get(url.searchParams.get('id')),name:url.searchParams.get('id')});
    if(action==='livery-studio')return json({message:'Fixture handoff accepted.'});
    return json({ok:true,enabled:false,entries:[]});
  }
  const studioBase=p.startsWith('/'+switchedToken+'/')?'/'+switchedToken+'/':'/studio/';
  if(p.startsWith(studioBase+'api/')){
    const action=p.slice((studioBase+'api/').length),switched=studioBase!=='/studio/';
    if(action==='editor-config')return json(switched?{...config,vehicle:otherCar}:config);
    if(action==='cars')return json({enabled:true,current:'1'.repeat(32),cars:[{...config.vehicle,id:'1'.repeat(32),name:'Fixture current car'},{...otherCar,id:'2'.repeat(32),name:'Fixture other car'}]});
    if(action==='car-switch'||action===`car-switch/${switchJobId}`)return json({id:switchJobId,status:holdCarPreparation?'preparing':'ready'});
    if(action===`car-switch/${switchJobId}/commit`){if(releaseCommit)await new Promise(resolve=>{releaseCommit=resolve;});return json({id:switchJobId,status:'committed',url:'/'+switchedToken+'/'});}
    if(action===`car-switch/${switchJobId}/cancel`)return json({id:switchJobId,status:'cancelled'});
    if(action==='manifest')return json(prepared.manifest);
    if(action==='language')return json({language:'en'});
    if(action==='preview-quality')return json({version:1,quality:'balanced'});
    if(action==='local-mesh')return file(res,path.join(car,prepared.files.mesh));
    if(action==='component-coverage')return file(res,path.join(car,prepared.files.coverage));
    if(action==='local-render/paint')return file(res,path.join(car,prepared.files.paint));
    if(action.startsWith('local-render/mask/'))return file(res,path.join(car,prepared.files.masks[Number(action.split('/').pop())]));
    if(action.startsWith('local-render/mask-raw/')){
      const image=PNG.sync.read(fs.readFileSync(path.join(car,prepared.files.masks[Number(action.split('/').pop())]))),header=Buffer.alloc(8);header.writeUInt32LE(image.width,0);header.writeUInt32LE(image.height,4);
      const data=Buffer.concat([header,image.data]);res.writeHead(200,{'Content-Type':'application/octet-stream','Content-Length':data.length});return res.end(data);
    }
    if(action.startsWith('native-texture/'))return file(res,path.join(car,prepared.files.native_textures[action.split('/').pop()]));
    if(action==='import-vinyl')return json({shapes:value.shapes});
    if(action==='render-vinyl')return json({png:preview,bounds:[800,400,1200,600]});
    if(action==='projects'&&value){studioSaved=value.project;fs.writeFileSync(path.join(run,'studio-saved.kfps-layout.json'),JSON.stringify(studioSaved));return json({entry:{id:studioProjectId,revision:'1',name:value.name}});}
    if(action==='projects')return json({entries:studioSaved?[{id:studioProjectId,revision:'1',name:'Studio test'}]:[],root_label:'Fixture per-car projects'});
    if(action==='projects/'+studioProjectId){if(releaseRestore)await new Promise(resolve=>{releaseRestore=resolve;});return json({entry:{id:studioProjectId,revision:'1',name:'Studio test'},project:switched?{...studioSaved,vehicle:otherCar}:studioSaved});}
    if(action.startsWith('projects/'))return json({error:'The saved project is missing.'},404);
    if(action==='recovery')return json(value?{entry:{id:'a'.repeat(32)}}:{version:1,entries:[]});
    if(action==='export-section')return json(sectionFailure?{error:'Fixture invalid section'}:{shapes:[shape]},sectionFailure?422:200);
    if(action==='export-experiment'){res.writeHead(200,{'Content-Type':'application/zip'});return res.end('fixture-zip');}
    if(action==='confirmation-preferences')return json({version:1,acknowledged:[]});
    return json({ok:true,entries:[]});
  }
  let base,relative;
  if(p.startsWith('/tools/fabric-editor/')){base=path.join(root,'KFPS.Editor/web');relative=p.slice('/tools/fabric-editor/'.length);}
  else if(p.startsWith(studioBase+'vendor/')){base=path.join(root,'tools/livery-inspector/vendor');relative=p.slice((studioBase+'vendor/').length);}
  else if(p.startsWith(studioBase)){relative=p.slice(studioBase.length)||'index.html';base=path.join(root,['release-announcement.css','release-announcement.js','activity-client.js'].includes(relative)?'KFPS.Editor/web':'tools/livery-studio/src/web');}
  else {base=root;relative=p.slice(1);}
  const target=path.resolve(base,relative);if(!target.startsWith(path.resolve(base)+path.sep)){res.writeHead(403);return res.end();}file(res,target);
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
  const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader']});
  const context=await browser.newContext({viewport:{width:1440,height:900},acceptDownloads:true});const errors=[];
  context.on('page',page=>page.on('pageerror',e=>errors.push(e.message)));
  const command=async(page,id)=>page.evaluate(id=>{const list=window.kfpsWorkspaceCommands.list();return window.kfpsWorkspaceCommands.execute(id,list.token);},id);
  try{
    const editor=await context.newPage();await editor.goto(origin+'/tools/fabric-editor/index.html');
    await editor.waitForFunction(()=>window.kfpsWorkspaceCommands,{},{timeout:30000});
    await editor.evaluate(()=>document.querySelectorAll('dialog[open]').forEach(d=>d.close()));
    assert.equal((await command(editor,'saveProject')).ok,false);
    await editor.evaluate(async shape=>{await loadPayload({shapes:[shape]});shortcuts.undo='Alt+Z';},shape);
    assert.equal(await editor.evaluate(()=>kfpsWorkspaceCommands.list().commands.find(c=>c.id==='undoBtn').shortcut),'Alt+Z');
    assert.equal(await editor.locator('.workspaceDocumentActions #openLiveryStudio').isVisible(),true);
    assert.equal((await command(editor,'openLiveryStudio')).ok,true);
    await editor.waitForFunction(()=>!document.getElementById('openLiveryStudio').disabled);
    await editor.evaluate(()=>{currentProjectName='Usability test';pushHistory('test');documentDirty=true;});
    assert.equal((await command(editor,'exportJson')).ok,true);
    await editor.waitForFunction(()=>!exportSaveInProgress);
    assert.ok(lastExport?.shapes[0].editor_group_path);assert.equal(await editor.evaluate(()=>documentDirty),true);
    assert.equal((await command(editor,'saveProject')).ok,true);await editor.waitForFunction(()=>!projectSaveInProgress);
    assert.equal(lastProject.format,'kloudy_fabric_editor_project_v1');assert.ok(lastProject.shapes[0].editor_group_path);
    assert.equal((await command(editor,'saveProjectAs')).ok,true);await editor.locator('#textPromptDialog').waitFor({state:'visible'});
    assert.match(await editor.locator('#textPromptDescription').textContent(),/internal project storage/);await editor.screenshot({path:path.join(run,'editor-save-project.png')});
    assert.equal(await editor.evaluate(()=>kfpsWorkspaceCommands.activity().running),true);
    await editor.locator('#textPromptCancel').click();await editor.waitForFunction(()=>!projectSaveInProgress);
    assert.equal(await editor.evaluate(()=>kfpsWorkspaceCommands.activity().running),false);
    await editor.evaluate(()=>{window.__releaseCommand=null;void editorCommands.enqueue(()=>new Promise(resolve=>{window.__releaseCommand=resolve;}),'test hold');});
    assert.equal((await command(editor,'exportJson')).ok,false);await editor.evaluate(()=>window.__releaseCommand());
    await editor.waitForFunction(()=>!editorCommands.busy);
    const stale=await editor.evaluate(()=>kfpsWorkspaceCommands.list());await editor.evaluate(async shape=>{await loadPayload({shapes:[shape]});},shape);
    assert.equal((await editor.evaluate(stale=>kfpsWorkspaceCommands.execute('saveProject',stale.token),stale)).error,'stale-context');
    await editor.locator('#workspaceSearch').click();await editor.locator('#workspaceCommandSearch input').fill('Appearance');
    await editor.screenshot({path:path.join(run,'editor-search-wide.png')});
    await editor.locator('[data-command-key="adjustTheme"]').click();assert.equal(await editor.locator('#themeAdjustDialog').isVisible(),true);
    assert.equal((await command(editor,'openJsonBrowser')).ok,false);await editor.evaluate(()=>document.querySelectorAll('dialog[open]').forEach(d=>d.close()));
    await editor.setViewportSize({width:900,height:700});await editor.locator('#workspaceSearch').click();
    await editor.screenshot({path:path.join(run,'editor-search-narrow.png')});
    await editor.evaluate(()=>document.getElementById('workspaceCommandSearch').close());
    const studio=await context.newPage();await studio.goto(origin+'/studio/');
    await studio.waitForFunction(()=>window.__liveryLab?.ready,{},{timeout:60000});
    assert.equal(await studio.evaluate(()=>kfpsWorkspaceSession.snapshot().reference.project),'');
    assert.equal((await command(studio,'exportSection')).ok,false);
    await studio.locator('#vinylFile').setInputFiles({name:'Synthetic.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({shapes:[shape]}))});
    await studio.waitForFunction(()=>window.__liveryLab.getProject().placements.length===1);
    await studio.waitForFunction(()=>!document.getElementById('saveProject').disabled);
    assert.equal(await studio.evaluate(()=>kfpsWorkspaceSession.snapshot().reference.dirty),true);
    const sourceDownload=studio.waitForEvent('download');await command(studio,'exportSource');await (await sourceDownload).saveAs(path.join(run,'studio-source.json'));
    assert.equal(await studio.evaluate(()=>kfpsWorkspaceSession.snapshot().reference.dirty),true);
    await studio.waitForFunction(()=>!document.getElementById('saveProject').disabled);
    assert.equal((await command(studio,'saveProject')).ok,true);await studio.locator('#layoutProjectName').fill('Studio test');
    assert.match(await studio.locator('#saveLayoutProject .storage-path').textContent(),/TOY_GR86_22.*3761/);assert.equal(await studio.evaluate(()=>kfpsWorkspaceCommands.activity().running),true);
    await studio.screenshot({path:path.join(run,'studio-save-project.png')});await studio.locator('[data-storage="save"]').click();
    await studio.waitForFunction(()=>!document.getElementById('saveLayoutProject').open);
    assert.equal(studioSaved.format,'kfps-livery-layout-v1');assert.equal(studioSaved.placements[0].section,'Left');
    const session=await studio.evaluate(()=>kfpsWorkspaceSession.snapshot());assert.equal(session.ready,true);assert.equal(session.reference.project,studioProjectId);assert.equal(session.reference.dirty,false);
    const restoreSession=async(ref,id)=>{await studio.evaluate(({ref,id})=>{void kfpsWorkspaceSession.restore(ref,id);},{ref,id});await studio.waitForFunction(id=>{const r=kfpsWorkspaceSession.snapshot().restore;return r?.requestId===id&&r.state!=='pending';},id);return studio.evaluate(()=>kfpsWorkspaceSession.snapshot().restore.state);};
    assert.equal(await restoreSession({car:session.reference.car,dirty:false},'car-only'),'restored');
    assert.equal(await restoreSession({...session.reference,car:{car_id:1,model_code:'other'}},'wrong-car'),'missing');
    assert.equal(await restoreSession({...session.reference,project:'../path'},'invalid-project'),'failed');
    assert.equal(await restoreSession({...session.reference,project:'c'.repeat(32)},'missing-project'),'missing');
    const beforeRestoreCommands=await studio.evaluate(()=>kfpsWorkspaceCommands.list());
    assert.equal(await restoreSession(session.reference,'exact-project'),'restored');
    assert.equal((await studio.evaluate(token=>kfpsWorkspaceCommands.execute('saveProject',token),beforeRestoreCommands.token)).error,'stale-context');
    assert.equal(await studio.locator('#openLayoutProject').isVisible(),false);
    assert.deepEqual(await studio.evaluate(()=>__liveryLab.getProject()),studioSaved);
    const restores=calls.filter(c=>c.path.endsWith('/projects/'+studioProjectId)).length;
    assert.equal(await restoreSession(session.reference,'exact-project'),'restored');assert.equal(calls.filter(c=>c.path.endsWith('/projects/'+studioProjectId)).length,restores);
    releaseRestore=true;
    await studio.evaluate(ref=>{void kfpsWorkspaceSession.restore(ref,'cancel-pending');},session.reference);
    await studio.waitForFunction(()=>kfpsWorkspaceSession.snapshot().restore.state==='pending');
    assert.equal(await studio.evaluate(()=>kfpsWorkspaceCommands.activity().running),true);
    await studio.evaluate(()=>kfpsWorkspaceSession.cancelRestore('cancel-pending'));
    for(let attempt=0;attempt<200&&typeof releaseRestore!=='function';attempt++)await new Promise(resolve=>setTimeout(resolve,10));
    assert.equal(typeof releaseRestore,'function');
    releaseRestore();releaseRestore=null;await studio.waitForFunction(()=>!kfpsWorkspaceCommands.activity().running);
    assert.equal(await studio.evaluate(()=>kfpsWorkspaceSession.snapshot().restore.state),'cancelled');
    assert.deepEqual(await studio.evaluate(()=>__liveryLab.getProject()),studioSaved);
    releaseRestore=true;
    await studio.evaluate(ref=>{void kfpsWorkspaceSession.restore(ref,'explicit-input');},session.reference);
    await studio.waitForFunction(()=>kfpsWorkspaceSession.snapshot().restore.state==='pending');
    await studio.locator('#workspaceSearch').click();
    assert.equal(await studio.evaluate(()=>kfpsWorkspaceSession.snapshot().restore.state),'cancelled');
    for(let attempt=0;attempt<200&&typeof releaseRestore!=='function';attempt++)await new Promise(resolve=>setTimeout(resolve,10));
    assert.equal(typeof releaseRestore,'function');releaseRestore();releaseRestore=null;
    await studio.evaluate(()=>document.getElementById('workspaceCommandSearch').close());
    assert.equal(JSON.parse(await studio.evaluate(()=>JSON.stringify(kfpsWorkspaceSession.snapshot()))).reference.project,studioProjectId);
    await studio.waitForFunction(()=>!document.getElementById('saveProject').disabled);
    await studio.locator('#duplicate').click();await studio.waitForFunction(()=>kfpsWorkspaceSession.snapshot().reference.dirty);
    const dirtyProject=await studio.evaluate(()=>__liveryLab.getProject());
    assert.equal(await restoreSession(session.reference,'dirty-live'),'busy');
    assert.equal(await restoreSession({...session.reference,dirty:true},'dirty-hint'),'recovery');
    await studio.locator('[data-recovery="dialog"]').waitFor({state:'visible'});
    assert.deepEqual(await studio.evaluate(()=>__liveryLab.getProject()),dirtyProject);
    await studio.locator('[data-recovery="close"]').click();
    const downloadPromise=studio.waitForEvent('download');assert.equal((await command(studio,'exportSection')).ok,true);const download=await downloadPromise;await download.saveAs(path.join(run,'studio-section.json'));
    assert.equal(JSON.parse(fs.readFileSync(path.join(run,'studio-section.json'))).shapes.length,1);
    assert.equal(await studio.evaluate(()=>kfpsWorkspaceSession.snapshot().reference.dirty),true);
    await studio.waitForFunction(()=>!document.getElementById('exportSection').disabled);
    sectionFailure=true;await command(studio,'exportSection');await studio.waitForFunction(()=>document.getElementById('sectionExportStatus').classList.contains('error'));sectionFailure=false;
    await command(studio,'exportExperiment');await studio.locator('#confirmExperiment').waitFor({state:'visible'});
    assert.match(await studio.locator('#experimentDestination').textContent(),/FH6.*Browser downloads.*Left/);await studio.screenshot({path:path.join(run,'studio-export-confirmation.png')});
    const before=calls.filter(c=>c.path.endsWith('export-experiment')).length;await studio.locator('#confirmExperiment [value="cancel"]').click();
    assert.equal(calls.filter(c=>c.path.endsWith('export-experiment')).length,before);
    await studio.locator('#workspaceSearch').click();await studio.locator('#workspaceCommandSearch input').fill('Export');
    await studio.screenshot({path:path.join(run,'studio-search-wide.png')});
    await studio.setViewportSize({width:900,height:700});await studio.screenshot({path:path.join(run,'studio-search-narrow.png')});
    for(const page of [editor,studio]){
      await page.evaluate(()=>{const dialog=document.getElementById('workspaceCommandSearch');if(!dialog.open)document.getElementById('workspaceSearch').click();});
      assert.equal(await page.locator('#workspaceCommandSearch').evaluate(d=>d.scrollWidth<=d.clientWidth+1),true);
      const result=await page.evaluate(()=>{document.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));const list=kfpsWorkspaceCommands.list();const result=kfpsWorkspaceCommands.execute(list.commands[0].id,list.token);document.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));return result;});assert.equal(result.ok,false);
      assert.equal(await page.evaluate(()=>{const before=kfpsWorkspaceCommands.list().token;document.getElementById('workspaceCommandSearch').close();document.getElementById('workspaceSearch').click();return before===kfpsWorkspaceCommands.list().token;}),true);
      await page.evaluate(()=>document.getElementById('workspaceCommandSearch').close());
    }
    await editor.setViewportSize({width:1440,height:900});await editor.locator('#workspaceViewMenu').click();await editor.locator('#editorThemeSelect').selectOption('dark');await editor.locator('#workspaceViewMenu').click();await editor.locator('#workspaceSearch').click();await editor.screenshot({path:path.join(run,'editor-search-dark.png')});
    await studio.evaluate(()=>KfpsStudioTheme.apply({id:'pastel',base:'pastel'}));await studio.locator('#workspaceSearch').click();await studio.screenshot({path:path.join(run,'studio-search-light.png')});
    await editor.close();await studio.close();
    const carRestore=await context.newPage();await carRestore.goto(origin+'/studio/');await carRestore.waitForFunction(()=>window.kfpsWorkspaceSession?.snapshot().ready);
    const otherRef={...session.reference,car:otherCar};
    holdCarPreparation=true;
    await carRestore.evaluate(ref=>{void kfpsWorkspaceSession.restore(ref,'cancel-car');},otherRef);
    await carRestore.locator('#carPicker').waitFor({state:'visible'});
    assert.equal(await carRestore.evaluate(()=>kfpsWorkspaceSession.snapshot().restore.state),'pending');
    await carRestore.evaluate(()=>kfpsWorkspaceSession.cancelRestore('cancel-car'));
    await carRestore.waitForFunction(()=>!kfpsWorkspaceCommands.activity().running);
    assert.equal(carRestore.url(),origin+'/studio/');assert.equal(calls.filter(c=>c.path.endsWith('/commit')).length,0);
    assert.equal(await carRestore.evaluate(()=>kfpsWorkspaceSession.snapshot().restore.state),'cancelled');
    assert.ok(calls.some(c=>c.path.endsWith(`/car-switch/${switchJobId}/cancel`)));
    holdCarPreparation=false;
    releaseCommit=true;
    await carRestore.evaluate(ref=>{void kfpsWorkspaceSession.restore(ref,'different-car');},otherRef);
    for(let attempt=0;attempt<500&&typeof releaseCommit!=='function';attempt++)await new Promise(resolve=>setTimeout(resolve,10));
    assert.equal(typeof releaseCommit,'function');
    assert.equal(await carRestore.evaluate(()=>kfpsWorkspaceSession.cancelRestore('different-car')),false);
    await carRestore.keyboard.press('Shift');
    assert.equal(await carRestore.evaluate(()=>kfpsWorkspaceSession.snapshot().restore.state),'pending');
    const commitActivity=await carRestore.evaluate(()=>kfpsWorkspaceCommands.activity());
    assert.equal(commitActivity.running,true);assert.match(commitActivity.status,/Opening the prepared car/);
    releaseCommit();releaseCommit=null;
    await carRestore.waitForURL(origin+'/'+switchedToken+'/',{timeout:20000});
    await carRestore.waitForFunction(()=>window.kfpsWorkspaceSession?.snapshot().ready);
    assert.deepEqual(await carRestore.evaluate(()=>kfpsWorkspaceSession.snapshot().reference.car),otherCar);
    assert.equal(await carRestore.evaluate(()=>kfpsWorkspaceSession.snapshot().restore),null);
    await carRestore.evaluate(ref=>{void kfpsWorkspaceSession.restore(ref,'different-car');},otherRef);
    await carRestore.waitForFunction(()=>kfpsWorkspaceSession.snapshot().restore?.state==='restored');
    assert.equal(await carRestore.evaluate(()=>kfpsWorkspaceSession.snapshot().reference.project),studioProjectId);
    assert.deepEqual(await carRestore.evaluate(()=>__liveryLab.getProject().vehicle),otherCar);
    assert.equal(calls.filter(c=>c.path.endsWith(`/car-switch/${switchJobId}/commit`)).length,1);
    await carRestore.goto(origin+'/studio/');await carRestore.waitForFunction(()=>window.kfpsWorkspaceSession?.snapshot().ready);
    await carRestore.evaluate(ref=>{void kfpsWorkspaceSession.restore({...ref,dirty:true},'other-car-recovery');},otherRef);
    await carRestore.waitForURL(origin+'/'+switchedToken+'/',{timeout:20000});await carRestore.waitForFunction(()=>window.kfpsWorkspaceSession?.snapshot().ready);
    await carRestore.evaluate(ref=>{void kfpsWorkspaceSession.restore({...ref,dirty:true},'other-car-recovery');},otherRef);
    await carRestore.locator('[data-recovery="dialog"]').waitFor({state:'visible'});
    assert.equal(await carRestore.evaluate(()=>kfpsWorkspaceSession.snapshot().restore.state),'recovery');
    assert.deepEqual(await carRestore.evaluate(()=>kfpsWorkspaceSession.snapshot().reference.car),otherCar);
    assert.equal(await carRestore.evaluate(()=>__liveryLab.getProject().placements.length),0);
    assert.equal(missing.length,0);
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(run,'browser-result.json'),JSON.stringify({browser:await browser.version(),mode:'real pages / fixture APIs / real prepared car assets',checks:['Editor toolbar handoff','custom binding label','export retains dirty state and groups','editable project receipt save','save cancellation / activity flags','edit queue busy guard','stale document rejection','search dispatch / modal block','Studio managed save / reopen','session exact project without picker','session duplicate request suppression','session missing car/project','session explicit cancellation','session trusted input cancellation','session dirty-live refusal / Recovery offer without apply','Qt JSON string snapshot','source and section export preserve dirty','section export / failure','experimental confirmation cancellation','wide/narrow popup','dark/light themes','IME rejection','opening popup preserves token'],errors,missing,calls},null,2));
    fs.writeFileSync(path.join(run,'commit-race-browser.json'),JSON.stringify({browser:await browser.version(),preparationCancellation:'accepted without commit',commitCancellation:'refused while reply delayed; pending retained',trustedInputDuringCommit:'pending retained',committedNavigation:'validated token page ready; exact project reopened',commitActivity,pageErrors:errors,missingAssets:missing},null,2));
    console.log('Headless Editor and Studio usability routes passed.');
  }catch(error){fs.writeFileSync(path.join(run,'browser-failure.json'),JSON.stringify({error:String(error),errors,missing,calls},null,2));throw error;}
  finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
