// Original 33-key palettes from isolated KFPS.Editor/web/style.css. Parity tested.
import {t,errorText} from './i18n.mjs';
export const FORMAT='kfps_fabric_editor_theme_v1';
export const PALETTES={"pastel":{"--bg":"#fff7fb","--shell":"#ffffff","--panel":"#fffafd","--panel2":"#ffeaf4","--panel3":"#fff0f7","--text":"#3d2632","--muted":"#8f6478","--soft":"#b78499","--line":"#f3bed4","--line2":"#e78daf","--accent":"#ec6fa4","--accent2":"#ffb8d4","--good":"#42b985","--warn":"#d98c22","--danger":"#e84469","--canvas-bg":"#ead0dc","--fabric-canvas-bg":"#ead0dc","--editor-grid-line":"rgba(91, 52, 70, 0.46)","--editor-grid-axis":"rgba(61, 38, 50, 0.66)","--editor-guide-line":"rgba(94, 52, 72, 0.92)","--editor-guide-selected":"rgba(54, 33, 45, 0.98)","--editor-guide-draft":"rgba(42, 26, 36, 0.96)","--editor-notch-line":"rgba(18, 16, 18, 0.92)","--editor-notch-muted":"rgba(18, 16, 18, 0.48)","--editor-notch-active":"rgba(236, 111, 164, 0.98)","--editor-selection-border":"#2b1622","--editor-shape-outline":"#151015","--editor-selection-corner":"#fffafd","--editor-selection-corner-stroke":"#2b1622","--editor-skew-corner":"#ec6fa4","--shape-tile-bg":"#fff4f9","--dialog-bg":"#fffafd","--dialog-header":"#ffe5f1"},"dark":{"--bg":"#080a10","--shell":"#0e111a","--panel":"#151925","--panel2":"#1b2030","--panel3":"#101521","--text":"#f2f5ff","--muted":"#9aa6c3","--soft":"#66708c","--line":"#30384f","--line2":"#475169","--accent":"#70e8ff","--accent2":"#b89cff","--good":"#72f0aa","--warn":"#ffd36e","--danger":"#ff5d7a","--canvas-bg":"#090b12","--fabric-canvas-bg":"#0b0d12","--editor-grid-line":"rgba(142, 170, 230, 0.34)","--editor-grid-axis":"rgba(220, 235, 255, 0.62)","--editor-guide-line":"rgba(236, 245, 255, 0.88)","--editor-guide-selected":"rgba(255, 255, 255, 0.98)","--editor-guide-draft":"rgba(236, 245, 255, 0.96)","--editor-notch-line":"rgba(255, 255, 255, 0.94)","--editor-notch-muted":"rgba(255, 255, 255, 0.46)","--editor-notch-active":"rgba(255, 255, 255, 1)","--editor-selection-border":"#ffffff","--editor-shape-outline":"#ffffff","--editor-selection-corner":"#111722","--editor-selection-corner-stroke":"#ffffff","--editor-skew-corner":"#70e8ff","--shape-tile-bg":"#111722","--dialog-bg":"#171b25","--dialog-header":"#202638"},"blackout":{"--bg":"#101010","--shell":"#141414","--panel":"#191919","--panel2":"#242424","--panel3":"#121212","--text":"#ededed","--muted":"#b6b6b6","--soft":"#aaaaaa","--line":"#777777","--line2":"#999999","--accent":"#c8ced4","--accent2":"#aeb7bd","--good":"#94c6a6","--warn":"#d8bb83","--danger":"#e1a0a0","--canvas-bg":"#1c1c1c","--fabric-canvas-bg":"#202020","--editor-grid-line":"rgba(210, 210, 210, 0.32)","--editor-grid-axis":"rgba(235, 235, 235, 0.64)","--editor-guide-line":"rgba(220, 220, 220, 0.9)","--editor-guide-selected":"#ffffff","--editor-guide-draft":"#dddddd","--editor-notch-line":"#ededed","--editor-notch-muted":"#999999","--editor-notch-active":"#ffffff","--editor-selection-border":"#f5f5f5","--editor-shape-outline":"#eeeeee","--editor-selection-corner":"#161616","--editor-selection-corner-stroke":"#f5f5f5","--editor-skew-corner":"#c8ced4","--shape-tile-bg":"#202020","--dialog-bg":"#191919","--dialog-header":"#242424"},"whiteout":{"--bg":"#f3f3f3","--shell":"#f7f7f7","--panel":"#fafafa","--panel2":"#e8e8e8","--panel3":"#ededed","--text":"#222222","--muted":"#555555","--soft":"#606060","--line":"#858585","--line2":"#737373","--accent":"#3f454a","--accent2":"#5a6269","--good":"#2e6145","--warn":"#7a5819","--danger":"#943c44","--canvas-bg":"#dedede","--fabric-canvas-bg":"#d4d4d4","--editor-grid-line":"rgba(45, 45, 45, 0.32)","--editor-grid-axis":"rgba(30, 30, 30, 0.68)","--editor-guide-line":"rgba(35, 35, 35, 0.92)","--editor-guide-selected":"#111111","--editor-guide-draft":"#333333","--editor-notch-line":"#222222","--editor-notch-muted":"#626262","--editor-notch-active":"#111111","--editor-selection-border":"#222222","--editor-shape-outline":"#222222","--editor-selection-corner":"#fafafa","--editor-selection-corner-stroke":"#222222","--editor-skew-corner":"#3f454a","--shape-tile-bg":"#f0f0f0","--dialog-bg":"#fafafa","--dialog-header":"#e8e8e8"}};
PALETTES['builtin:xbox']={
  '--bg':'#111713','--shell':'#161d19','--panel':'#202923','--panel2':'#2b352d',
  '--panel3':'#101612','--text':'#eef3e8','--muted':'#c9d3c4','--soft':'#acbba7',
  '--line':'#5f7462','--line2':'#778a79','--accent':'#a1e52c','--accent2':'#f1d45c',
  '--good':'#a1e52c','--warn':'#f1cf64','--danger':'#ff9290',
  '--canvas-bg':'#101310','--fabric-canvas-bg':'#252725',
  '--editor-grid-line':'rgba(193, 201, 188, 0.28)','--editor-grid-axis':'rgba(226, 231, 223, 0.6)',
  '--editor-guide-line':'#f1cf64','--editor-guide-selected':'#ffe0a5','--editor-guide-draft':'#c1c9bc',
  '--editor-notch-line':'#eef3e8','--editor-notch-muted':'#acbba7','--editor-notch-active':'#a1e52c',
  '--editor-selection-border':'#a1e52c','--editor-shape-outline':'#eef3e8',
  '--editor-selection-corner':'#101612','--editor-selection-corner-stroke':'#a1e52c',
  '--editor-skew-corner':'#f1cf64','--shape-tile-bg':'#161d19',
  '--dialog-bg':'#202923','--dialog-header':'#2b352d',
};
PALETTES['builtin:ps2']={
  '--bg':'#050506','--shell':'#101013','--panel':'#1a1a20','--panel2':'#2a2a30',
  '--panel3':'#101014','--text':'#f2f2f7','--muted':'#d1d1dc','--soft':'#bdbdcd',
  '--line':'#5b5b68','--line2':'#737383','--accent':'#7ba9ff','--accent2':'#e6a9cc',
  '--good':'#9bd6bf','--warn':'#edd498','--danger':'#ff9daf',
  '--canvas-bg':'#111113','--fabric-canvas-bg':'#262628',
  '--editor-grid-line':'rgba(206, 206, 220, 0.28)','--editor-grid-axis':'rgba(232, 232, 241, 0.6)',
  '--editor-guide-line':'#edd498','--editor-guide-selected':'#ffe6ba','--editor-guide-draft':'#bdbdcd',
  '--editor-notch-line':'#f2f2f7','--editor-notch-muted':'#bdbdcd','--editor-notch-active':'#7ba9ff',
  '--editor-selection-border':'#7ba9ff','--editor-shape-outline':'#f2f2f7',
  '--editor-selection-corner':'#101014','--editor-selection-corner-stroke':'#7ba9ff',
  '--editor-skew-corner':'#e6a9cc','--shape-tile-bg':'#16161b',
  '--dialog-bg':'#1a1a20','--dialog-header':'#2a2a30',
};
export const COLOR_KEYS=Object.freeze(Object.keys(PALETTES.pastel));
export const STORAGE_KEY='kfps.livery.studio.theme.v1';
const names={pastel:'Signature Pink',dark:'Dark',blackout:'Blackout',whiteout:'Whiteout','builtin:xbox':'Original Xbox','builtin:ps2':'Original PS2'};
const labels=['App background','Outer shell','Main panels','Raised panels','Inset panels','Main text','Muted text','Soft labels','Thin borders','Strong borders','Primary accent','Secondary accent','Success color','Warning color','Danger color','Canvas surround','Canvas color','Grid lines','Grid axis','Guide lines','Selected guide','Guide draft','Rotation notch','Muted notch','Active notch','Selection border','Shape outline','Transform handles','Handle stroke','Skew handle','Shape tile background','Dialog background','Dialog header'];
const familyDefault='"Segoe UI", "Trebuchet MS", sans-serif';
const maxBytes=256*1024;
const plain=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const bounded=(value,fallback,max=128)=>typeof value==='string'&&value.trim()?value.trim().slice(0,max):fallback;
function inferredScheme(value,base) {
  let rgb;
  if(/^#[a-f0-9]{3,8}$/i.test(value||'')){
    const hex=value.slice(1),six=hex.length<=4?hex.slice(0,3).split('').map(c=>c+c).join(''):hex.slice(0,6);
    rgb=[0,2,4].map(i=>parseInt(six.slice(i,i+2),16));
  }else if(/^rgba?\(/.test(value||''))rgb=value.match(/[\d.]+/g)?.slice(0,3).map(Number);
  return rgb?.length===3?(.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]>145?'light':'dark'):base==='pastel'||base==='whiteout'?'light':'dark';
}

export function safeColor(value,supports=globalThis.CSS?.supports?.bind(globalThis.CSS)) {
  if(typeof value!=='string'||!value.trim()||value.length>200)throw Error('A theme color is invalid or too long.');
  const color=value.trim();
  if(!/^[a-z0-9#.,%+()/ -]+$/i.test(color)||/\b(?:url|var|env|attr|expression|image|paint)\s*\(|\b(?:inherit|initial|unset|revert|revert-layer|currentcolor)\b/i.test(color))throw Error('Theme colors cannot contain URLs, CSS references or declarations.');
  for(const match of color.matchAll(/([a-z][a-z0-9-]*)\s*\(/gi))if(!['rgb','rgba','hsl','hsla','hwb','lab','lch','oklab','oklch','color','color-mix'].includes(match[1].toLowerCase()))throw Error('Unsupported theme color function.');
  if(supports&&!supports('color',color))throw Error('A theme color is not supported.');
  return color;
}

export function safeFontFamily(value=familyDefault) {
  if(typeof value!=='string'||value.length>256||!value.trim()||!/^[-\p{L}\p{N} _'",.]+$/u.test(value))throw Error('Invalid theme font family.');
  const families=value.split(',');if(families.length>8)throw Error('Too many font families.');
  return families.map(raw=>{
    const item=raw.trim(),quote=item[0];
    const name=(quote==='"'||quote==="'")&&item.at(-1)===quote?item.slice(1,-1):item;
    if(!name||/["']/.test(name))throw Error('Invalid theme font family.');
    return ['serif','sans-serif','monospace','system-ui','cursive','fantasy'].includes(name)?name:JSON.stringify(name);
  }).join(', ');
}

export function normalizeTheme(input,{supportsColor}={}) {
  if(!plain(input))throw Error('Expected a theme object.');
  if(JSON.stringify(input).length>maxBytes)throw Error('Theme exceeds the 256 KiB limit.');
  if(input.format!==undefined&&input.format!==FORMAT)throw Error('Unsupported theme format.');
  const base=Object.hasOwn(PALETTES,input.base)?input.base:Object.hasOwn(PALETTES,input.id)?input.id:'pastel';
  const supplied=input.variables??input.values??{};
  if(!plain(supplied))throw Error('Theme colors must be an object.');
  const values={...PALETTES[base]};
  for(const key of COLOR_KEYS)if(Object.hasOwn(supplied,key))values[key]=safeColor(supplied[key],supportsColor);
  return {format:FORMAT,id:bounded(input.id,base),name:bounded(input.name,names[base]),base,values,
    fontFamily:safeFontFamily(input.fontFamily??familyDefault),
    colorScheme:['light','dark'].includes(input.colorScheme)?input.colorScheme:inferredScheme(values['--panel'],base)};
}

export function resolveThemeContext(data) {
  // An explicit null host is the default, not the effective Studio override.
  const host=Object.hasOwn(data,'host_ui_theme')?data.host_ui_theme:data.ui_theme;
  const fallback={id:'dark',base:'dark'};
  return {host:normalizeTheme(host??fallback),effective:normalizeTheme(data.ui_theme??fallback),
    hostFonts:host?.fonts??[],effectiveFonts:data.ui_theme?.fonts??[]};
}

export function authorizedFonts(value) {
  if(value===undefined)return [];
  if(!Array.isArray(value)||value.length>4)throw Error('Invalid theme font list.');
  return value.map(font=>{
    if(!plain(font)||typeof font.url!=='string'||!/^\.\/api\/ui-font\/[a-f0-9]{64}$/.test(font.url))throw Error('Theme font URL is not an authorized local asset.');
    const cssFamily=safeFontFamily(font.family);if(cssFamily.includes(','))throw Error('A font asset needs one family.');
    // FontFace takes a family name, not the quoted CSS font-family declaration.
    const family=cssFamily.startsWith('"')?JSON.parse(cssFamily):cssFamily;
    const weight=String(font.weight??'400'),style=font.style??'normal';
    if(!/^(?:[1-9]00|normal|bold)$/.test(weight)||!['normal','italic','oblique'].includes(style))throw Error('Invalid theme font descriptor.');
    return {family,url:font.url,weight,style};
  });
}

function installTooltips() {
  const controller=new AbortController(),{signal}=controller,tooltip=document.createElement('div');
  tooltip.id='studioTooltip';tooltip.role='tooltip';tooltip.hidden=true;
  let target=null,title='',previousDescription=null;
  const hide=()=>{
    if(target){if(!target.hasAttribute('title'))target.setAttribute('title',title);if(previousDescription===null)target.removeAttribute('aria-describedby');else target.setAttribute('aria-describedby',previousDescription);}
    target=null;tooltip.hidden=true;
  };
  const show=node=>{
    const next=node?.closest?.('[title]');if(!next||next===target||!next.title)return;
    hide();target=next;title=next.title;previousDescription=next.getAttribute('aria-describedby');next.removeAttribute('title');
    next.setAttribute('aria-describedby',[previousDescription,tooltip.id].filter(Boolean).join(' '));tooltip.textContent=title;
    (next.closest('dialog')||document.body).append(tooltip);tooltip.hidden=false;
    const box=next.getBoundingClientRect(),tip=tooltip.getBoundingClientRect();
    tooltip.style.left=Math.max(8,Math.min(innerWidth-tip.width-8,box.left))+'px';
    tooltip.style.top=Math.max(8,box.bottom+8+tip.height<innerHeight?box.bottom+8:box.top-tip.height-8)+'px';
  };
  document.addEventListener('pointerover',event=>show(event.target),{signal});
  document.addEventListener('focusin',event=>show(event.target),{signal});
  document.addEventListener('pointerout',event=>{if(target&&!target.contains(event.relatedTarget))hide();},{signal});
  for(const event of ['focusout','pointerdown','keydown','scroll'])document.addEventListener(event,hide,{capture:true,signal});
  window.addEventListener('blur',hide,{signal});window.addEventListener('resize',hide,{signal});
  return ()=>{hide();controller.abort();tooltip.remove();};
}

export async function initializeTheme({fetcher=globalThis.fetch.bind(globalThis),storage}={}) {
  if(storage===undefined)try{storage=globalThis.localStorage;}catch{storage=null;}
  const $=id=>document.getElementById(id),root=document.documentElement;
  const stop=new AbortController(),loadedFonts=new Map();
  let disposed=false,revision=0,dialogRevision=0,current,committed,draft,restore,host,config={},warning='',persistence=false,saving=false;
  let refreshPending=false,refreshFlight=null,hostFonts=[],draftFonts=[];
  function syncChromeMotion() {
    if(disposed||root.dataset.editorThemeBase!=='builtin:xbox')delete root.dataset.xboxMotion;
    else root.dataset.xboxMotion=!document.hidden&&document.hasFocus()?'running':'paused';
    if(disposed||root.dataset.editorThemeBase!=='builtin:ps2')delete root.dataset.ps2Motion;
    else root.dataset.ps2Motion=!document.hidden&&document.hasFocus()?'running':'paused';
  }
  document.addEventListener('visibilitychange',syncChromeMotion,{signal:stop.signal});
  for(const event of ['focus','blur','pageshow'])window.addEventListener(event,syncChromeMotion,{signal:stop.signal});
  const notice=(text,error=false)=>{
    if(error)text=errorText(text);
    $('themeStatus').textContent=text;$('themeStatus').classList.toggle('error',error);
    $('themeNotice').textContent=error?text:'';$('themeNotice').hidden=!error;
  };
  async function request(path,body) {
    const controller=new AbortController(),abort=()=>controller.abort();stop.signal.addEventListener('abort',abort,{once:true});
    const timer=setTimeout(abort,5000);
    try {
      const response=await fetcher('./api/'+path,{signal:controller.signal,cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
      const text=await response.text();if(text.length>maxBytes)throw Error('Theme response exceeds its size limit.');
      let data;try{data=JSON.parse(text);}catch{throw Error('Theme response is not valid JSON.');}
      if(!response.ok)throw Error(typeof data.error==='string'?data.error.slice(0,512):'Theme request failed.');
      return data;
    } finally {clearTimeout(timer);stop.signal.removeEventListener('abort',abort);}
  }
  function canvasColor(value) {
    const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
    const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.fillStyle=value;ctx.fillRect(0,0,1,1);
    const [r,g,b]=ctx.getImageData(0,0,1,1).data;
    return '#'+[r,g,b].map(n=>n.toString(16).padStart(2,'0')).join('');
  }
  async function fontsFor(fonts) {
    for(const descriptor of fonts) {
      const key=JSON.stringify(descriptor);if(loadedFonts.has(key))continue;
      const face=new FontFace(descriptor.family,`url("${descriptor.url}")`,{weight:descriptor.weight,style:descriptor.style});
      let timer;
      try {
        await Promise.race([face.load(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('The theme font could not load within five seconds.')),5000);})]);
        if(disposed)return;document.fonts.add(face);loadedFonts.set(key,face);
      } finally{clearTimeout(timer);}
    }
  }
  async function apply(input,{source='studio',fonts=[],isCurrent=()=>true}={}) {
    const theme=normalizeTheme(input),serial=++revision;
    let fontWarning='';
    try{await fontsFor(authorizedFonts(fonts));}catch(error){fontWarning=error.message;}
    if(disposed||serial!==revision||!isCurrent())return false;
    for(const key of COLOR_KEYS)root.style.setProperty(key,theme.values[key]);
    root.style.setProperty('--canvas-background',canvasColor(theme.values['--fabric-canvas-bg']));
    root.style.setProperty('--ui-font-family',theme.fontFamily);root.style.colorScheme=theme.colorScheme;
    root.dataset.editorThemeBase=theme.base;root.dataset.editorTheme=theme.id;root.dataset.themeSource=source;
    syncChromeMotion();
    current=theme;warning=fontWarning;
    window.dispatchEvent(new CustomEvent('kfps-theme-applied',{detail:{id:theme.id,name:theme.name,source}}));
    notice(fontWarning||theme.name,Boolean(fontWarning));return true;
  }
  function remember(theme) {
    try{storage?.setItem(STORAGE_KEY,JSON.stringify({theme}));}catch{notice(t('Theme applied for this session; browser storage is unavailable.'),true);}
  }
  async function persist(theme) {
    if(persistence) {
      const result=await request('ui-theme',{theme});
      const context=resolveThemeContext(result);
      await apply(context.effective,{source:theme?'studio':'host',fonts:context.effectiveFonts});
      config={...config,...result};host=context.host;hostFonts=context.hostFonts;
    } else {
      await apply(theme||host,{source:theme?'studio':'host',fonts:theme?draftFonts:hostFonts});
    }
    remember(theme);committed={theme:structuredClone(current),source:theme?'studio':'host'};
    if(!persistence)notice(t('Theme applied. This server retains selection only in this browser origin.'),true);
  }
  function refreshHost() {
    refreshPending=true;
    if(disposed||$('themeDialog').open||saving)return Promise.resolve(false);
    if(refreshFlight)return refreshFlight;
    refreshFlight=(async()=>{
      let refreshed=false;
      while(refreshPending&&!disposed&&!$('themeDialog').open&&!saving) {
        refreshPending=false;
        const ticket=dialogRevision,data=await request('editor-config');
        // A dialog may open, close, or save while the request/fonts are loading.
        // Re-fetch after that decision; never replay a stale host response.
        const stillCurrent=()=>ticket===dialogRevision&&!$('themeDialog').open&&!saving;
        if(!stillCurrent()){refreshPending=true;continue;}
        const context=resolveThemeContext(data);
        if(committed.source==='host'||data.ui_theme?.source==='studio') {
          const applied=await apply(context.effective,{source:data.ui_theme?.source==='studio'?'studio':'host',fonts:context.effectiveFonts,isCurrent:stillCurrent});
          if(!applied){if(!disposed)refreshPending=true;continue;}
          committed={theme:structuredClone(current),source:root.dataset.themeSource};
        }
        config=data;host=context.host;hostFonts=context.hostFonts;refreshed=true;
      }
      return refreshed;
    })().finally(()=>{refreshFlight=null;});
    return refreshFlight;
  }
  function resumeRefresh() {
    if(refreshPending)void refreshHost().catch(error=>{if(!disposed)notice(t`Theme refresh failed: ${errorText(error)}`,true);});
  }
  function fields() {
    const basic=new Set(['--shell','--panel','--text','--accent','--fabric-canvas-bg','--line']);
    $('themeColors').replaceChildren();$('themeAdvancedColors').replaceChildren();
    for(const key of COLOR_KEYS) {
      const label=document.createElement('label');label.className='theme-color';
      const text=document.createElement('span');text.textContent=t(labels[COLOR_KEYS.indexOf(key)]);
      const swatch=document.createElement('input');swatch.type='color';swatch.value=canvasColor(draft.values[key]);swatch.setAttribute('aria-label',t`${text.textContent} swatch`);
      const input=document.createElement('input');input.type='text';input.maxLength=200;input.value=draft.values[key];input.dataset.themeVar=key;input.setAttribute('aria-label',t`${text.textContent} color`);
      label.append(text,swatch,input);(basic.has(key)?$('themeColors'):$('themeAdvancedColors')).append(label);
      const update=async value=>{
        if(saving)return;
        dialogRevision++;
        try{const next=normalizeTheme({...draft,values:{...draft.values,[key]:value}});draft=next;input.value=value;input.removeAttribute('aria-invalid');swatch.value=canvasColor(value);await preview(true);}
        catch(error){input.setAttribute('aria-invalid','true');notice(error.message,true);updateButtons();}
      };
      input.addEventListener('input',()=>void update(input.value));swatch.addEventListener('input',()=>void update(swatch.value));
    }
    $('themeName').value=draft.name;$('themeFont').value=draft.fontFamily;$('themeScheme').value=draft.colorScheme;
    for(const id of ['themeName','themeFont','themeScheme'])$(id).removeAttribute('aria-invalid');
    updateButtons();
  }
  function invalid(){return Boolean($('themeDialog').querySelector('[aria-invalid=true]'));}
  function updateButtons(){for(const id of ['applyTheme','downloadTheme'])$(id).disabled=saving||invalid();$('themeCancel').disabled=saving;$('themeControls').disabled=saving;}
  async function preview(custom=false) {
    if(custom){$('themeChoice').value='custom';if(Object.hasOwn(PALETTES,draft.id))draft.id='studio-custom';}
    await apply(draft,{source:'preview',fonts:draftFonts});updateButtons();
  }
  function selectOptions() {
    const select=$('themeChoice');select.replaceChildren();
    for(const [value,label] of [['host','Follow KFPS'],...Object.entries(names),['custom','Custom theme']]){
      const option=document.createElement('option');option.value=value;option.textContent=t(label);select.append(option);
    }
    select.value=committed.source==='host'?'host':Object.hasOwn(names,current.id)?current.id:'custom';
  }
  function open() {
    if(disposed||saving)return;
    dialogRevision++;
    restore={...structuredClone(committed),fonts:config.ui_theme?.fonts||[]};draft=structuredClone(current);draftFonts=restore.fonts;
    selectOptions();fields();$('themeDialog').showModal();
  }
  async function cancel() {
    if(saving)return;
    dialogRevision++;
    if(restore)await apply(restore.theme,{source:restore.source,fonts:restore.fonts});restore=null;
    $('themeDialog').close();
    resumeRefresh();
  }
  $('showTheme').addEventListener('click',open,{signal:stop.signal});
  $('themeCancel').addEventListener('click',()=>void cancel(),{signal:stop.signal});
  $('themeDialog').addEventListener('cancel',event=>{event.preventDefault();void cancel();},{signal:stop.signal});
  $('themeChoice').addEventListener('change',async()=>{
    if(saving)return;
    dialogRevision++;
    const value=$('themeChoice').value;
    if(value==='custom')return;
    draft=structuredClone(value==='host'?host:normalizeTheme({id:value,base:value}));draftFonts=value==='host'?hostFonts:[];fields();await preview();
  },{signal:stop.signal});
  for(const [id,key] of [['themeName','name'],['themeFont','fontFamily'],['themeScheme','colorScheme']])$(id).addEventListener('input',async()=>{
    if(saving)return;
    dialogRevision++;
    try{draft=normalizeTheme({...draft,[key]:$(id).value});$(id).removeAttribute('aria-invalid');await preview(true);}
    catch(error){$(id).setAttribute('aria-invalid','true');notice(error.message,true);updateButtons();}
  },{signal:stop.signal});
  $('importTheme').addEventListener('click',()=>{if(!saving)$('themeFile').click();},{signal:stop.signal});
  $('themeFile').addEventListener('change',async()=>{
    const file=$('themeFile').files?.[0];if(!file||saving)return;
    const ticket=++dialogRevision;
    try{if(file.size>maxBytes)throw Error('Theme file exceeds 256 KiB.');const text=await file.text();if(ticket!==dialogRevision||!$('themeDialog').open||saving||disposed)return;const data=JSON.parse(text);if(data.format!==FORMAT)throw Error('Select a KFPS editor theme JSON.');draft=normalizeTheme(data);$('themeChoice').value='custom';fields();await preview();}
    catch(error){if(ticket===dialogRevision&&!disposed)notice(error.message,true);}finally{$('themeFile').value='';}
  },{signal:stop.signal});
  $('downloadTheme').addEventListener('click',()=>{
    if(saving||invalid())return;
    const value=normalizeTheme({...draft,name:$('themeName').value});const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download='studio-theme.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  },{signal:stop.signal});
  $('applyTheme').addEventListener('click',async()=>{
    if(saving||invalid())return;saving=true;dialogRevision++;updateButtons();
    try{const follow=$('themeChoice').value==='host';await persist(follow?null:draft);restore=null;$('themeDialog').close();}
    catch(error){notice(t`Theme was not saved: ${errorText(error)}`,true);}finally{saving=false;updateButtons();resumeRefresh();}
  },{signal:stop.signal});
  const disposeTooltips=installTooltips();
  window.addEventListener('pagehide',()=>{disposed=true;syncChromeMotion();stop.abort();disposeTooltips();for(const face of loadedFonts.values())document.fonts.delete(face);loadedFonts.clear();},{once:true});
  try{config=await request('editor-config');}catch(error){warning=error.message;}
  persistence=config.ui_theme_persistence===true;
  let initial;
  try{const context=resolveThemeContext(config);host=context.host;hostFonts=context.hostFonts;initial=context.effective;}catch(error){warning=error.message;host=initial=normalizeTheme({id:'dark',base:'dark'});}
  let source=config.ui_theme?.source==='studio'?'studio':'host';
  if(!persistence)try{const cached=JSON.parse(storage?.getItem(STORAGE_KEY)||'null');if(cached?.theme){initial=normalizeTheme(cached.theme);source='studio';}}catch{warning='The saved Studio theme was invalid; the current KFPS theme was used.';}
  const startupWarning=warning;
  await apply(initial,{source,fonts:config.ui_theme?.fonts});committed={theme:structuredClone(current),source};
  if(startupWarning)notice(startupWarning,true);
  root.removeAttribute('data-theme-loading');
  $('showTheme').disabled=false;
  const api=Object.freeze({getTheme:()=>structuredClone(current),getState:()=>({source:root.dataset.themeSource,persistence,warning}),
    apply:async value=>{const next=normalizeTheme(value);await persist(next);},
    refresh:refreshHost});
  window.addEventListener('focus',()=>{void api.refresh().catch(error=>notice(t`Theme refresh failed: ${errorText(error)}`,true));},{signal:stop.signal});
  window.addEventListener('kfps-theme-refresh',()=>{void api.refresh().catch(error=>notice(t`Theme refresh failed: ${errorText(error)}`,true));},{signal:stop.signal});
  window.KfpsStudioTheme=api;return api;
}
