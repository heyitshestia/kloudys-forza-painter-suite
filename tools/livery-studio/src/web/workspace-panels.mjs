import {t} from './i18n.mjs';

// Move existing controls, preserving their handlers and document transactions.
export function initializeWorkspacePanels({canLeave=()=>true,icon=()=>{}}={}) {
  const $=id=>document.getElementById(id),host=$('authoring'),stop=new AbortController();
  if(!host||$('inspectorTabs'))throw Error('Studio inspector is already mounted or unavailable.');
  const signal=stop.signal,undo=[],panels=new Map(),tabs=new Map(),scroll=new Map();
  const nav=document.createElement('nav');nav.id='inspectorTabs';nav.setAttribute('role','tablist');
  nav.setAttribute('aria-label',t('Inspector'));
  const body=document.createElement('div');body.id='inspectorBody';
  const sections=[['placement','Placement','Move'],['design','Design','Palette'],
    ['car','Car','Shapes'],['view','View','Focus'],['project','Project','FolderOpen']];
  let active='',disposed=false;
  host.classList.add('tabbed-inspector');host.prepend(nav,body);

  function move(node,target){
    if(!node)return;
    const parent=node.parentNode,next=node.nextSibling;
    undo.push(()=>parent.insertBefore(node,next?.parentNode===parent?next:null));
    target.append(node);
  }
  function expand(node){
    for(const detail of [node,...node.querySelectorAll('details')]){
      if(detail.tagName!=='DETAILS')continue;
      const summary=detail.querySelector(':scope > summary');
      if(!summary)continue;
      const open=detail.open,role=summary.getAttribute('role'),level=summary.getAttribute('aria-level'),tabindex=summary.getAttribute('tabindex');
      detail.open=true;detail.classList.add('inspector-section');
      summary.setAttribute('role','heading');summary.setAttribute('aria-level','2');summary.tabIndex=-1;
      summary.addEventListener('click',event=>event.preventDefault(),{signal});
      summary.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key))event.preventDefault();},{signal});
      undo.push(()=>{
        detail.open=open;detail.classList.remove('inspector-section');
        for(const [name,value] of [['role',role],['aria-level',level],['tabindex',tabindex]]){
          if(value===null)summary.removeAttribute(name);else summary.setAttribute(name,value);
        }
      });
    }
  }
  function show(name,{focus=false,force=false}={}){
    if(disposed||!panels.has(name))return false;
    if(active!==name&&!force&&!canLeave())return false;
    if(active!==name){
      if(active)scroll.set(active,body.scrollTop);
      active=name;
      for(const [key,panel] of panels){
        panel.hidden=key!==name;
        tabs.get(key).setAttribute('aria-selected',String(key===name));
        tabs.get(key).tabIndex=key===name?0:-1;
      }
      body.scrollTop=scroll.get(name)||0;
      try{sessionStorage.setItem('kfps.studio.inspector.v1',name);}catch{}
    }
    if(focus)tabs.get(name).focus({preventScroll:true});
    return true;
  }
  function reveal(node,options){
    if(typeof node==='string')node=$(node);
    for(const [name,panel] of panels)if(node&&panel.contains(node))return show(name,options);
    return false;
  }
  for(const [name,label,symbol] of sections){
    const button=document.createElement('button');button.type='button';button.id=`inspector-tab-${name}`;
    button.dataset.inspectorTab=name;button.dataset.icon=symbol;button.textContent=t(label);button.title=t(label);
    button.setAttribute('role','tab');button.setAttribute('aria-controls',`inspector-${name}`);icon(button);
    const panel=document.createElement('section');panel.id=`inspector-${name}`;panel.className='inspector-panel';
    panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',button.id);panel.hidden=true;
    tabs.set(name,button);panels.set(name,panel);nav.append(button);body.append(panel);
    button.addEventListener('click',()=>show(name),{signal});
    button.addEventListener('keydown',event=>{
      const keys=sections.map(s=>s[0]),index=keys.indexOf(name);
      const target={ArrowRight:keys[(index+1)%keys.length],ArrowLeft:keys[(index+keys.length-1)%keys.length],Home:keys[0],End:keys.at(-1)}[event.key];
      if(target){event.preventDefault();event.stopPropagation();show(target,{focus:true});}
    },{signal});
  }
  // Command search and shortcuts use the same buttons even in an inactive tab.
  host.addEventListener('click',event=>{
    const button=event.target.closest?.('button');
    if(button?.closest('.inspector-panel')?.hidden&&!reveal(button)){
      event.preventDefault();event.stopImmediatePropagation();
    }
  },{capture:true,signal});
  for(const [name,ids] of [
    ['placement',['properties','selectionTools']],
    ['design',['sectionPanel','colourTools','symmetryTools','sourceEditTools']],
    ['car',['componentPanel']],
    ['view',['inspectionToolsHost','fidelityPanel','languageSettings']],
    ['project',['recoveryToolsHost','exportDetails']],
  ])for(const id of ids){const node=$(id);if(node){expand(node);move(node,panels.get(name));}}
  const confirmations=$('resetConfirmations')?.closest('details');
  if(confirmations){expand(confirmations);move(confirmations,panels.get('view'));}
  const exports=$('exportExperiment')?.parentElement;
  if(exports)move(exports,panels.get('project'));

  const quality=$('previewQuality'),qualityHost=quality?.closest('.preview-quality-controls');
  let observer;
  if(qualityHost){
    move(qualityHost,$('editTools'));qualityHost.classList.add('toolbar-quality');
    const field=quality.closest('.field'),hidden=quality.hidden;
    quality.hidden=true;field.classList.add('quality-original');
    const group=document.createElement('div');group.className='quality-buttons segmented';
    group.setAttribute('role','group');group.setAttribute('aria-label',t('Vinyl preview quality'));
    const label=document.createElement('span');label.className='quality-caption';label.textContent=t('Preview');
    const buttons=[];
    for(const [value,title] of [['fast','Fast'],['balanced','Balanced'],['sharp','Sharp']]){
      const button=document.createElement('button');button.type='button';button.dataset.qualityChoice=value;
      button.textContent=t(title);button.title=[...quality.options].find(o=>o.value===value)?.textContent||t(title);
      button.setAttribute('aria-describedby','previewQualityStatus');buttons.push(button);group.append(button);
      button.addEventListener('click',()=>{
        if(quality.disabled||!canLeave())return;
        quality.value=value;quality.dispatchEvent(new Event('change',{bubbles:true}));syncQuality();
      },{signal});
    }
    function syncQuality(){for(const button of buttons){button.disabled=quality.disabled;button.setAttribute('aria-pressed',String(button.dataset.qualityChoice===quality.value));}}
    qualityHost.prepend(label,group);
    observer=new MutationObserver(syncQuality);observer.observe(quality,{attributes:true,attributeFilter:['disabled']});
    quality.addEventListener('change',syncQuality,{signal});syncQuality();
    undo.push(()=>{qualityHost.classList.remove('toolbar-quality');field.classList.remove('quality-original');quality.hidden=hidden;group.remove();label.remove();});
  }
  // Restore the tab only; document data and other user preferences are untouched.
  let initial='placement';
  try{const value=sessionStorage.getItem('kfps.studio.inspector.v1');if(panels.has(value))initial=value;}catch{}
  show(initial,{force:true});
  function dispose(){
    if(disposed)return;disposed=true;stop.abort();observer?.disconnect();
    for(const restore of undo.reverse())restore();
    nav.remove();body.remove();host.classList.remove('tabbed-inspector');
  }
  window.addEventListener('pagehide',dispose,{once:true,signal});
  return {show,reveal,dispose};
}
