import en from './locales/en.mjs';
import ko from './locales/ko.mjs';
import ja from './locales/ja.mjs';

export const LOCALES=Object.freeze({en:'English',ko:'한국어',ja:'日本語'});
const packs={en,ko,ja};
let language='en';
export const getLanguage=()=>language;
export function setLanguage(value){
  if(typeof value!=='string'||!Object.hasOwn(packs,value))throw Error('Unsupported Studio language.');
  language=value;
}
export function t(source,...values){
  const key=Array.isArray(source)?source.reduce((text,part,index)=>text+(index?`{${index-1}}`:'')+part,''):source;
  const template=packs[language][key]??en[key]??key;
  // Single pass: interpolation values (including user names) are opaque text.
  return values.length?template.replace(/\{(\d+)\}/g,(token,index)=>Number(index)<values.length?String(values[index]):token):template;
}
export const number=value=>Number(value).toLocaleString({en:'en-US',ko:'ko-KR',ja:'ja-JP'}[language]);
export const date=value=>new Date(value).toLocaleString({en:'en-US',ko:'ko-KR',ja:'ja-JP'}[language]);
const sections={All:'All',Top:'Top',Left:'Left',Right:'Right',Front:'Front',Back:'Back',FrontWindshield:'Front windshield',BackWindshield:'Back windshield',TopWindow:'Top window',LeftWindow:'Left window',RightWindow:'Right window'};
export const sectionLabel=value=>Object.hasOwn(sections,value)?t(sections[value]):value;
const states={pending:'Pending',opened:'Editor opened',editing:'Editing',ready:'Ready to apply',taken:'Artwork received',cancelled:'Cancelled',failed:'Failed',preparing:'Preparing',cancelling:'Cancelling',committed:'Completed'};
export const stateLabel=value=>Object.hasOwn(states,value)?t(states[value]):value;

// Only call on a known static template, before appending any user/server data.
// No observers, global interception, attribute values or live-document rescans.
export function localizeStatic(root){
  const visit=node=>{
    if(node.nodeType===3){
      const raw=node.nodeValue,key=raw.trim();
      if(Object.hasOwn(en,key))node.nodeValue=raw.replace(key,t(key));
      return;
    }
    if(node.nodeType!==1&&node.nodeType!==11)return;
    if(['SCRIPT','STYLE','CODE','PRE','SVG','TEXTAREA'].includes(node.tagName))return;
    for(const key of ['title','aria-label','placeholder']){
      const value=node.getAttribute?.(key);
      if(value&&Object.hasOwn(en,value))node.setAttribute(key,t(value));
    }
    for(const child of node.childNodes)visit(child);
  };
  visit(root);
}

// Errors from validation and the local host retain their raw diagnostic when
// unknown. Known literal messages are translated, never arbitrary substrings.
export function errorText(error){
  const text=String(error?.message??error??'');
  if(language==='en')return text;
  if(Object.hasOwn(en,text))return t(text);
  for(const [key,pattern] of diagnosticPatterns){
    const match=pattern.exec(text);
    if(match)return t(key,...match.slice(1));
  }
  return text;
}
const escapeRegex=text=>text.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
// Bounded exact templates for trusted model/host diagnostics only. Substituted
// names and paths are copied verbatim; unknown diagnostics stay intact.
const diagnosticKeys=new Set([
  'Invalid {0}.','{0} must be between {1} and {2}.','Invalid {0}: {1}.',
  'Texture load failed ({0}).','Car mesh load failed ({0}).','Request failed (HTTP {0}).',
  'Unknown component type: {0}','Unavailable component option: {0}',
  'UV3: {0}/{1} paint/glass meshes present; {2} missing, {3} invalid. {4} visible surfaces remain neutral/unmapped.',
  '{0} native parameter applications across {1} mesh instances. {2} texture references remain unresolved. Physical shading and parameter colour encoding are approximations, not native shader parity.',
  '{0} body/glass surface(s) retained without supported vinyl mapping in this preview. In-game paintability is unverified.',
  'Source options: {0} declared, {1} converted, {2} unrepresented.',
  'Source options: {0} declared, {1} converted, {2} unrepresented, {3} blocked.',
  'UV integrity errors: {0}. Source UV equivalence is not established.',
  '{0} option(s) have no tagged meshes; empty versus missing is not confirmed.',
  'Source-aware studio materials; {0} native wheel instances; {1} placeholder wheels.',
  'Source-aware studio materials; {0} native wheel instances; {1} placeholder wheels (hidden).',
  'Neutral inspection materials; {0} native wheel instances; {1} placeholder wheels.',
  'Neutral inspection materials; {0} native wheel instances; {1} placeholder wheels (hidden).'
]);
const diagnosticPatterns=Object.keys(en).filter(key=>diagnosticKeys.has(key))
  .sort((a,b)=>b.replace(/\{\d+\}/g,'').length-a.replace(/\{\d+\}/g,'').length)
  .map(key=>[key,new RegExp('^'+key.split(/\{\d+\}/g).map(escapeRegex).join('([\\s\\S]*?)')+'$')]);

export async function initializeLanguage({fetcher=globalThis.fetch.bind(globalThis),root=document}={}){
  const select=root.getElementById('studioLanguage'),save=root.getElementById('saveLanguage'),status=root.getElementById('languageStatus');
  let saved='en',loaded=false,disposed=false,saving=false;
  const controllers=new Set();
  const request=async value=>{
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);controllers.add(controller);
    try{
      const response=await fetcher('./api/language',{signal:controller.signal,cache:'no-store',...(value===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({language:value})})});
      if(!response.ok)throw Error('Language preference could not be saved or loaded.');
      const result=await response.json();
      if(!result||typeof result.language!=='string'||!Object.hasOwn(LOCALES,result.language)||value!==undefined&&result.language!==value)throw Error('Invalid language preference response.');
      return result.language;
    }finally{clearTimeout(timer);controllers.delete(controller);}
  };
  let startupError=false;
  try{saved=await request();loaded=true;}catch{startupError=true;}
  setLanguage(saved);root.documentElement.lang=saved;
  localizeStatic(root.body);
  const settings=root.getElementById('languageSettings');
  if(settings)Object.assign(settings.style,{display:'flex',flexWrap:'wrap',alignItems:'center',gap:'8px',padding:'8px 12px',borderTop:'1px solid var(--line)',background:'var(--panel)',color:'var(--text)'});
  for(const id of ['section','studioLanguage']){
    const label=root.querySelector?.(`label[for="${id}"]`);
    if(label)label.style.whiteSpace='nowrap';
  }
  const artworkHeading=root.querySelector?.('#library > .section-heading h1');
  if(artworkHeading){artworkHeading.style.whiteSpace='nowrap';artworkHeading.parentElement.style.flexWrap='wrap';}
  const feedback=(text,error=false)=>{if(status){status.textContent=text;status.classList.toggle('error',error);}};
  const update=()=>{if(save)save.disabled=saving||loaded&&select.value===saved;};
  if(select){
    select.replaceChildren(...Object.entries(LOCALES).map(([code,label])=>{const option=root.createElement('option');option.value=code;option.textContent=label;return option;}));
    select.value=saved;select.disabled=false;
    select.addEventListener('change',()=>{feedback('');update();});
  }
  save?.addEventListener('click',async()=>{
    if(saving||disposed||!select||!Object.hasOwn(LOCALES,select.value))return;
    const next=select.value;saving=true;select.disabled=true;update();feedback(t('Saving language...'));
    try{await request(next);if(disposed)return;saved=next;loaded=true;feedback(t('Language saved. Applies next time you open Studio.'));}
    catch{if(!disposed)feedback(t('Language was not saved. Try again.'),true);}
    finally{saving=false;if(!disposed){select.disabled=false;update();if(!save.disabled)save.focus({preventScroll:true});}}
  });
  if(startupError)feedback(t('Language preference could not be read. English is used for this session.'),true);
  update();
  const dispose=()=>{disposed=true;for(const controller of controllers)controller.abort();};
  root.defaultView?.addEventListener('pagehide',dispose,{once:true});
  return {getState:()=>({active:language,saved,loaded,saving}),dispose};
}
