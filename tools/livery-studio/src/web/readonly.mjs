import {normalizeTheme, COLOR_KEYS, safeFontFamily} from './theme-adapter.mjs';
import {setLanguage, localizeStatic} from './i18n.mjs';

let themeRevision=0;
const loadedFonts=new Map();
async function applyTheme(input) {
  const revision=++themeRevision;
  const theme=normalizeTheme(input),root=document.documentElement;
  const requestedFonts=Array.isArray(input.fontAssets)?input.fontAssets.slice(0,3):[];
  const wanted=new Set(requestedFonts.map(font=>font.asset+':'+safeFontFamily(font.family)));
  for(const [key,face] of loadedFonts)if(!wanted.has(key)){document.fonts.delete(face);loadedFonts.delete(key);}
  for(const key of COLOR_KEYS)root.style.setProperty(key,theme.values[key]);
  root.style.setProperty('--canvas-background',theme.values['--fabric-canvas-bg']);
  root.style.setProperty('--ui-font-family',theme.fontFamily);
  root.style.colorScheme=theme.colorScheme;
  window.dispatchEvent(new Event('kfps-theme-applied'));
  for(const font of requestedFonts) {
    if(typeof font.asset!=='string'||font.asset.length>180||!/^[A-Za-z0-9_./ -]+$/.test(font.asset))continue;
    const family=safeFontFamily(font.family),key=font.asset+':'+family;
    if(loadedFonts.has(key))continue;
    const encoded=Array.from(new TextEncoder().encode(font.asset),n=>n.toString(16).padStart(2,'0')).join('');
    const face=new FontFace(family.startsWith('"')?JSON.parse(family):family,`url('./api/ui-font/${encoded}')`);
    try {
      await face.load();
      if(revision!==themeRevision)return;
      document.fonts.add(face);loadedFonts.set(key,face);
    } catch { /* A missing font retains the theme's readable family fallback. */ }
  }
}
window.__kfpsReadonlyTheme=input=>{void applyTheme(input).catch(()=>{});};
window.__kfpsReadonlyLanguage=language=>{setLanguage(language);localizeStatic(document);};
await applyTheme({id:'dark',base:'dark'});
for(const button of document.querySelectorAll('[data-icon]')) {
  const nodes=window.KfpsIconNodes?.[button.dataset.icon];if(!nodes)continue;
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
  for(const [key,value] of Object.entries({viewBox:'0 0 24 24',fill:'none',stroke:'currentColor','stroke-width':'1.8','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);
  for(const [tag,attrs] of nodes){const node=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);svg.append(node);}
  button.prepend(svg);
}
window.addEventListener('pagehide',()=>{themeRevision++;for(const face of loadedFonts.values())document.fonts.delete(face);loadedFonts.clear();},{once:true});
try {
  await import('./livery-scene.js');
} catch(error) {
  const message=String(error?.message||error),status=document.getElementById('status');
  status.textContent=message;status.classList.add('error');status.classList.remove('hidden');
  console.info('KFPS_VIEWER:'+JSON.stringify({event:'error',message}));
}
