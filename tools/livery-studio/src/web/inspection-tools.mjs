import {setInspectionMode, inspectionState, focusInspectionSection} from './livery-scene.js';
import {t,localizeStatic,sectionLabel,number,errorText} from './i18n.mjs';

// Match only identical authored positions. Do not weld nearby surfaces or invent UVs.
export function uv3SeamSegments(geometry) {
  const position=geometry?.getAttribute('position'),uv=geometry?.getAttribute('uv3');
  const empty={available:false,positions:new Float32Array(),boundaries:0,discontinuities:0};
  if(!position||!uv||uv.count!==position.count)return empty;
  const count=geometry.index?.count??position.count;
  if(count%3||count>1800000)return empty;
  const points=[],coordinates=[];
  for(let i=0;i<position.count;i++){
    const p=[position.getX(i),position.getY(i),position.getZ(i)],t=[uv.getX(i),uv.getY(i)];
    if(!p.every(Number.isFinite)||!t.every(Number.isFinite))return empty;
    points.push(p);coordinates.push(t);
  }
  const edges=new Map(),vertex=i=>geometry.index?geometry.index.getX(i):i;
  for(let i=0;i<count;i+=3){
    const triangle=[vertex(i),vertex(i+1),vertex(i+2)];
    if(!triangle.every(index=>Number.isInteger(index)&&index>=0&&index<points.length))return empty;
    for(let j=0;j<3;j++){
      let a=triangle[j],b=triangle[(j+1)%3],ka=points[a].join(','),kb=points[b].join(',');
      if(ka===kb)continue;
      if(ka>kb){[a,b]=[b,a];[ka,kb]=[kb,ka];}
      const key=ka+'|'+kb,values=[...coordinates[a],...coordinates[b]],previous=edges.get(key);
      if(previous){previous.count++;previous.split||=values.some((value,k)=>Math.abs(value-previous.uv[k])>1e-6);}
      else edges.set(key,{a,b,uv:values,count:1,split:false});
    }
  }
  const lines=[];let boundaries=0,discontinuities=0;
  for(const edge of edges.values()){
    if(edge.count===1)boundaries++;else if(edge.split)discontinuities++;else continue;
    lines.push(...points[edge.a],...points[edge.b]);
  }
  return {available:true,positions:new Float32Array(lines),boundaries,discontinuities};
}

export function initInspection({host,message=()=>{},isBusy=()=>false}) {
  if(!(host instanceof HTMLElement))throw Error('An inspection controls host is required.');
  if(typeof isBusy!=='function')throw Error('Inspection busy state must be a function.');
  const existing=host.querySelector('[data-inspection-controls]');
  if(existing)throw Error('Inspection controls are already mounted.');
  const stop=new AbortController(),signal=stop.signal;
  const root=document.createElement('details');root.dataset.inspectionControls='';root.open=true;
  root.innerHTML='<summary>Surface inspection</summary><div class="segmented" role="group" aria-label="Surface inspection mode"></div><ul aria-label="Inspection legend"></ul><label class="field">Section close-up<select aria-label="Inspection section"></select></label><button type="button" data-inspection-focus>Frame section</button><p role="status" aria-live="polite"></p>';
  localizeStatic(root);root.style.cssText='border-top:1px solid var(--line);padding-bottom:8px;min-width:0;color:var(--text)';
  const modes=root.querySelector('[role=group]'),legend=root.querySelector('ul'),select=root.querySelector('select'),status=root.querySelector('[role=status]');
  legend.style.cssText='list-style:none;padding:0;margin:8px 0;font-size:12px;overflow-wrap:anywhere';
  status.style.cssText='font-size:12px;color:var(--muted);overflow-wrap:anywhere';
  const buttons=new Map();let disposed=false,sectionSignature='';
  for(const [mode,label] of [['off','Off'],['paintability','Paintability'],['uv-seams','UV seams']]){
    const button=document.createElement('button');button.type='button';button.textContent=t(label);button.dataset.inspectionMode=mode;
    button.setAttribute('aria-pressed','false');button.title=t(mode==='off'?'Restore normal materials':mode==='paintability'?'Inspect native mask eligibility for the active sections':'Show authored UV3 island boundaries and discontinuities');
    button.addEventListener('click',()=>setMode(mode),{signal});modes.append(button);buttons.set(mode,button);
  }
  for(const [label,color,pattern] of [
    ['Paint eligible','--accent','solid'],['Glass eligible','--warn','dots'],['Unsupported mapping','--danger','stripes'],
    ['Outside active masks','--muted','solid'],['UV3 boundary / discontinuity','--accent','line']]){
    const item=document.createElement('li'),swatch=document.createElement('span');
    item.style.cssText='display:flex;align-items:center;gap:7px;min-height:21px';
    swatch.setAttribute('aria-hidden','true');swatch.style.cssText=`display:inline-block;flex:none;width:18px;height:12px;border:1px solid var(--line);background:var(${color},var(--text))`;
    if(pattern==='stripes')swatch.style.background=`repeating-linear-gradient(135deg,var(${color}) 0 3px,var(--panel) 3px 6px)`;
    if(pattern==='dots')swatch.style.background=`radial-gradient(var(--panel) 1px,transparent 1px),var(${color},var(--accent))`;
    if(pattern==='dots')swatch.style.backgroundSize='5px 5px';
    if(pattern==='line')swatch.style.height='2px';
    item.append(swatch,document.createTextNode(t(label)));legend.append(item);
  }
  function refresh(){
    if(disposed)return;
    const state=inspectionState(),blocked=Boolean(isBusy());
    for(const [mode,button] of buttons){button.disabled=!state.ready||blocked;button.setAttribute('aria-pressed',String(state.mode===mode));}
    const signature=JSON.stringify(state.sections);
    if(signature!==sectionSignature){
      const selected=select.value;select.replaceChildren();
      for(const name of state.sections){const option=document.createElement('option');option.value=name;option.textContent=sectionLabel(name);select.append(option);}
      if(state.sections.includes(selected))select.value=selected;sectionSignature=signature;
    }
    select.disabled=!state.ready||blocked;root.querySelector('[data-inspection-focus]').disabled=!state.ready||blocked||!state.sections.length;
    legend.hidden=state.mode==='off';
    status.textContent=!state.ready?t('Preview unavailable'):state.mode==='uv-seams'?t`${number(state.lineSegments)} UV3 edges`+(state.seamUnavailable?t`; ${state.seamUnavailable} meshes unavailable`:''):t(state.mode==='paintability'?'Native masks / active sections':'Normal materials');
  }
  function setMode(mode){
    if(disposed||isBusy())return false;
    try{const accepted=setInspectionMode(mode);refresh();return accepted;}
    catch(error){message(errorText(error),true);return false;}
  }
  root.querySelector('[data-inspection-focus]').addEventListener('click',()=>{
    if(disposed||isBusy())return;
    if(!focusInspectionSection(select.value))message(t('No eligible surface is available for this section.'),true);
  },{signal});
  window.addEventListener('kfps-inspection-change',refresh,{signal});
  window.addEventListener('kfps-viewer-error',refresh,{signal});
  host.append(root);refresh();
  return {setMode,refresh,dispose(){if(disposed)return;disposed=true;stop.abort();setInspectionMode('off');root.remove();}};
}
