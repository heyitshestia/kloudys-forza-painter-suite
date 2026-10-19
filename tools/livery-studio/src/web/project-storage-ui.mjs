import {t,errorText,localizeStatic} from './i18n.mjs';

export function createProjectSaveController({api,getProject}) {
  let current=null,generation=0,pending=false,disposed=false;
  const copy=value=>value?structuredClone(value):null;
  return {
    entry:()=>copy(current),
    adopt(entry){current=copy(entry);generation++;},
    async save(value,{replace=null}={}) {
      if(disposed)throw Error('The editor is closed.');
      if(pending)throw Error('A project save is already in progress.');
      const name=typeof value==='string'?value.trim().normalize('NFC'):'';
      if(!name||[...name].length>80||/[\x00-\x1f\x7f]/.test(name))throw Error('Enter a project name of 1 to 80 characters without control characters.');
      const project=structuredClone(getProject()),epoch=generation;
      const target=replace||(current?.name===name?current:null);
      const payload={name,project,...(target?{id:target.id,expected_revision:target.revision}:{})};
      pending=true;
      try {
        const response=await api('projects',payload);
        if(!response.entry||typeof response.entry.id!=='string'||typeof response.entry.revision!=='string')throw Error('The saved project response is invalid.');
        const active=!disposed&&epoch===generation;
        if(active)current=copy(response.entry);
        return {entry:copy(response.entry),project,current:active};
      } finally {pending=false;}
    },
    dispose(){disposed=true;generation++;current=null;},
  };
}

export function initProjectStorage({api,getProject,getDocumentRevision=()=>JSON.stringify(getProject()),onModalChange=()=>{},loadProject,importVinyl,readVinyl,externalProject,externalVinyl,defaultName,message,doc=document,win=window}) {
  const controller=createProjectSaveController({api,getProject});
  let disposed=false,generation=0,working=false,resolveSave=null,conflict=null,projectEntries=[],libraryEntries=[],path='',nextOffset=null,nextProjectOffset=null;
  const make=(tag,text='',attrs={})=>{const node=doc.createElement(tag);node.textContent=text;for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);return node;};
  const button=(text,id)=>make('button',text,{type:'button','data-storage':id});
  const status=()=>make('p','',{class:'experiment-status',role:'status','aria-live':'polite'});
  const dialog=(id,title)=>{const node=make('dialog','',{id,class:'storage-dialog','aria-labelledby':`${id}Title`});node.append(make('h2',title,{id:`${id}Title`}));return node;};
  const actions=(...nodes)=>{const row=make('div','',{class:'actions'});row.append(...nodes);return row;};
  const saveDialog=dialog('saveLayoutProject','Save livery project'),saveStatus=status();
  const name=make('input','',{type:'text',id:'layoutProjectName',maxlength:'160',autocomplete:'off',spellcheck:'false'});
  const nameField=make('label','Project name',{class:'field',for:name.id});nameField.append(name);
  const saveRoot=make('p','',{class:'storage-path'});
  const save=button('Save','save'),replace=button('Replace saved project','replace'),cancelSave=button('Cancel','cancel-save');replace.hidden=true;
  saveDialog.append(nameField,saveRoot,saveStatus,actions(cancelSave,replace,save));
  const openDialog=dialog('openLayoutProject','Open livery project'),openStatus=status();
  const projectRoot=make('p','',{class:'storage-path'}),projectList=make('select','',{size:'9','aria-label':'Saved livery projects','data-storage':'projects'});
  const open=button('Open selected','open'),refresh=button('Refresh','refresh'),moreProjects=button('Load more','more-projects'),browseProject=button('Browse elsewhere...','browse-project'),closeOpen=button('Cancel','cancel-open');
  openDialog.append(projectRoot,projectList,moreProjects,openStatus,actions(browseProject,refresh,closeOpen,open));
  const vinylDialog=dialog('vinylLibraryPicker','Add vinyl'),vinylStatus=status(),libraryRoot=make('p','',{class:'storage-path'});
  const up=button('Up one folder','up'),libraryPath=make('span','',{class:'storage-path'}),navigation=make('div','',{class:'storage-navigation'});navigation.append(up,libraryPath);
  const libraryList=make('div','',{class:'storage-files','aria-label':'Vinyl folders and files','data-storage':'library'});
  const add=button('Add selected vinyl','add'),more=button('Load more','more'),browseVinyl=button('Browse elsewhere...','browse-vinyl'),closeVinyl=button('Cancel','cancel-vinyl');
  vinylDialog.append(libraryRoot,navigation,libraryList,more,vinylStatus,actions(browseVinyl,closeVinyl,add));
  const dialogs=[saveDialog,openDialog,vinylDialog];
  dialogs.forEach(node=>{localizeStatic(node);doc.body.append(node);});
  let selectedVinyl=null,openRevision=null;
  function feedback(node,value,error=false){node.textContent=error?errorText(value):t(value);node.classList.toggle('error',error);}
  function controls(){
    for(const node of dialogs)for(const control of node.querySelectorAll('button,input,select'))control.disabled=working;
    open.disabled=working||!projectList.value;add.disabled=working||!selectedVinyl;
    more.hidden=nextOffset===null;moreProjects.hidden=nextProjectOffset===null;up.disabled=working||!path;
  }
  function start(node){if(disposed||working||dialogs.some(item=>item.open))return false;generation++;node.returnValue='cancel';node.showModal();controls();onModalChange();return true;}
  async function request(node,statusNode,callback){
    if(working||disposed||!node.open)return;
    working=true;controls();const epoch=generation;
    const isCurrent=()=>!disposed&&epoch===generation&&node.open;
    try{await callback(isCurrent);}catch(error){if(isCurrent())feedback(statusNode,error,true);}
    finally{working=false;if(!disposed)controls();}
  }
  function finishSave(result){const resolve=resolveSave;resolveSave=null;saveDialog.close(result?'saved':'cancel');resolve?.(result);}
  async function submitSave(overwrite=false){
    await request(saveDialog,saveStatus,async isCurrent=>{
      feedback(saveStatus,'Saving project...');
      try{
        const result=await controller.save(name.value,{replace:overwrite?conflict:null});
        if(isCurrent()&&result.current)finishSave(result);
      }catch(error){
        if(isCurrent()&&['project_exists','project_changed'].includes(error.code)&&error.entry){
          conflict=error.entry;replace.hidden=false;
          feedback(saveStatus,error.code==='project_changed'?'This project was changed in another window. Replace that version, or choose a different name.':'A project with this name already exists. Replace it, or choose a different name.',true);
        }else throw error;
      }
    });
  }
  save.addEventListener('click',()=>void submitSave());replace.addEventListener('click',()=>void submitSave(true));
  name.addEventListener('input',()=>{conflict=null;replace.hidden=true;feedback(saveStatus,'');});
  name.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing&&event.keyCode!==229&&!working){event.preventDefault();void submitSave();}});
  cancelSave.addEventListener('click',()=>finishSave(null));
  saveDialog.addEventListener('close',()=>{generation++;if(resolveSave){const resolve=resolveSave;resolveSave=null;resolve(null);}});

  async function listProjects(offset=0){await request(openDialog,openStatus,async isCurrent=>{
    feedback(openStatus,'Loading projects...');const response=await api(`projects?offset=${offset}`);if(!isCurrent())return;
    const previous=projectList.value;projectEntries=offset?[...projectEntries,...response.entries]:response.entries||[];projectRoot.textContent=response.root_label||'';nextProjectOffset=response.next_offset??null;
    projectList.replaceChildren(...projectEntries.map(entry=>make('option',entry.name,{value:entry.id})));
    if(projectEntries.some(entry=>entry.id===previous))projectList.value=previous;
    feedback(openStatus,projectEntries.length?'':'No saved projects for this car yet.');
  });}
  async function openSelected(){await request(openDialog,openStatus,async isCurrent=>{
    const id=projectList.value;if(!projectEntries.some(entry=>entry.id===id))return;
    feedback(openStatus,'Opening project...');const response=await api(`projects/${encodeURIComponent(id)}`);if(!isCurrent())return;
    const isLayoutCurrent=()=>isCurrent()&&openRevision===getDocumentRevision();
    if(!isLayoutCurrent())throw Error('The current layout changed. Nothing was opened.');
    await loadProject(response.project,{isCurrent:isLayoutCurrent});if(!isCurrent())return;
    controller.adopt(response.entry);openDialog.close('opened');message('Layout project opened.');
  });}
  projectList.addEventListener('change',controls);projectList.addEventListener('dblclick',()=>void openSelected());
  open.addEventListener('click',()=>void openSelected());refresh.addEventListener('click',()=>void listProjects());
  moreProjects.addEventListener('click',()=>{if(nextProjectOffset!==null)void listProjects(nextProjectOffset);});
  closeOpen.addEventListener('click',()=>openDialog.close());
  browseProject.addEventListener('click',()=>{const revision=openRevision;openDialog.close();externalProject({isCurrent:()=>revision===getDocumentRevision()});});

  function fileIcon(node,kind){
    const nodes=win.KfpsIconNodes?.[kind==='directory'?'FolderOpen':'Shapes'];if(!nodes)return;
    const ns='http://www.w3.org/2000/svg',svg=doc.createElementNS(ns,'svg');
    for(const [key,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.8','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);
    for(const [tag,attrs] of nodes){const child=doc.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))child.setAttribute(key,value);svg.append(child);}node.prepend(svg);
  }
  function renderLibrary(){
    libraryList.replaceChildren(...libraryEntries.map(entry=>{
      const node=button(entry.name,entry.kind==='directory'?'folder':'file');node.dataset.path=entry.path;
      node.setAttribute('aria-pressed',String(entry.path===selectedVinyl?.path));fileIcon(node,entry.kind);
      node.addEventListener('click',()=>{
        if(working)return;if(entry.kind==='directory'){void listLibrary(entry.path);return;}selectedVinyl=entry;
        for(const row of libraryList.querySelectorAll('button'))row.setAttribute('aria-pressed',String(row.dataset.path===entry.path));
        controls();
      });
      if(entry.kind!=='directory')node.addEventListener('dblclick',()=>{if(working)return;selectedVinyl=entry;void addSelected();});
      return node;
    }));
  }
  async function listLibrary(nextPath,offset=0){await request(vinylDialog,vinylStatus,async isCurrent=>{
    feedback(vinylStatus,'Loading vinyl folder...');const response=await api(`vinyl-library?path=${encodeURIComponent(nextPath)}&offset=${offset}`);if(!isCurrent())return;
    path=response.path||'';libraryPath.textContent=path||'imgs';libraryRoot.textContent=response.root_label||'';
    selectedVinyl=null;libraryEntries=offset?[...libraryEntries,...response.entries]:response.entries;nextOffset=response.next_offset??null;
    renderLibrary();feedback(vinylStatus,libraryEntries.length?'':'No vinyl JSON files in this folder.');
  });}
  async function addSelected(){await request(vinylDialog,vinylStatus,async isCurrent=>{
    const entry=selectedVinyl;if(!entry)return;feedback(vinylStatus,'Opening vinyl...');
    const file=await readVinyl(entry);if(!isCurrent())return;await importVinyl(file,{isCurrent});
    if(isCurrent())vinylDialog.close('added');
  });}
  up.addEventListener('click',()=>void listLibrary(path.split('/').slice(0,-1).join('/')));
  more.addEventListener('click',()=>{if(nextOffset!==null)void listLibrary(path,nextOffset);});
  add.addEventListener('click',()=>void addSelected());closeVinyl.addEventListener('click',()=>vinylDialog.close());
  browseVinyl.addEventListener('click',()=>{vinylDialog.close();externalVinyl();});
  for(const node of dialogs){
    node.addEventListener('cancel',event=>{if(working)event.preventDefault();});
    node.addEventListener('close',()=>{if(!disposed)onModalChange();});
    if(node!==saveDialog)node.addEventListener('close',()=>{generation++;});
  }
  // A disabled field may briefly focus body; modal shortcuts must still not edit the car.
  const modalKeys=event=>{
    if(!dialogs.some(node=>node.open))return;
    const composing=event.isComposing||event.keyCode===229||event.getModifierState?.('AltGraph');
    const inside=event.target?.nodeType&&dialogs.some(node=>node.contains(event.target));
    if(!composing&&(event.ctrlKey||event.metaKey)&&!event.altKey&&(event.code==='KeyS'||!inside&&['KeyZ','KeyY','KeyD'].includes(event.code))){event.preventDefault();event.stopImmediatePropagation();}
    else if(event.target?.nodeType&&!dialogs.some(node=>node.contains(event.target)))event.stopImmediatePropagation();
  };
  win.addEventListener('keydown',modalKeys,{capture:true});
  return {
    adopt:entry=>controller.adopt(entry),
    isOpen:()=>!disposed&&dialogs.some(node=>node.open),
    async save(){
      if(!start(saveDialog))return null;
      conflict=null;replace.hidden=true;feedback(saveStatus,'');name.value=controller.entry()?.name||defaultName();
      saveRoot.textContent=t('Saved in this car\'s project folder.');name.focus();name.select();
      return new Promise(resolve=>{resolveSave=resolve;});
    },
    open(){if(start(openDialog)){openRevision=getDocumentRevision();void listProjects();}},
    addVinyl(){if(start(vinylDialog)){path='';selectedVinyl=null;libraryEntries=[];nextOffset=null;renderLibrary();void listLibrary('');}},
    dispose(){if(disposed)return;disposed=true;generation++;controller.dispose();resolveSave?.(null);resolveSave=null;win.removeEventListener('keydown',modalKeys,{capture:true});for(const node of dialogs)node.remove();},
  };
}
