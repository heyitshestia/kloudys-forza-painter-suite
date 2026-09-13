import {korean} from './report-ko.mjs';

const KEY='kfps-report-language-v1', listeners=new Set(), originals=new WeakMap();
const choices=new Set(['auto','en','ko']);
let choice='auto';
try {const saved=globalThis.localStorage?.getItem(KEY);if(choices.has(saved))choice=saved;} catch {}
export function language() {
  if(choice!=='auto')return choice;
  const detected=globalThis.KFPSReportSystemLanguage || globalThis.navigator?.language || 'en';
  return detected.toLowerCase().startsWith('ko')?'ko':'en';
}
export function registerStrings(entries) {Object.assign(korean,entries);}
export function t(source,...args) {
  // Known localized notices can be redrawn when the user switches languages.
  const key=Object.hasOwn(korean,source)?source:Object.keys(korean).find(key=>korean[key]===source)||source;
  const value=language()==='ko'?(korean[key]||key):key;
  return String(value).replace(/\{(\d+)\}/g,(all,index)=>args[index]===undefined?all:String(args[index]));
}
export function onLanguageChange(callback) {listeners.add(callback);return ()=>listeners.delete(callback);}
export function setLanguage(value) {
  if(!choices.has(value))return false;
  choice=value;
  try {localStorage.setItem(KEY,value);} catch {}
  applyLanguage();for(const callback of listeners)callback();
  return true;
}
export function applyLanguage() {
  if(!globalThis.document)return;
  document.documentElement.lang=language();
  for(const node of document.querySelectorAll('[data-i18n]')){
    const key=node.dataset.i18n||originals.get(node)||node.textContent;
    originals.set(node,key);node.textContent=t(key);
  }
  for(const attribute of ['placeholder','aria-label','title'])for(const node of document.querySelectorAll(`[data-i18n-${attribute}]`)){
    node.setAttribute(attribute,t(node.getAttribute(`data-i18n-${attribute}`)));
  }
  const select=document.getElementById('report-language');
  if(select){select.value=choice;select.onchange=()=>setLanguage(select.value);}
}
export function localizedError(text) {
  const value=String(text||'');
  if(Object.hasOwn(korean,value)||Object.values(korean).includes(value)||language()==='en')return t(value);
  if(/[가-힣]/.test(value))return value;
  const support=value.match(/^(.+) Support code: ([a-z-]+-\d{1,3})\.$/);
  if(support)return localizedError(support[1])+' '+t('Support code: {0}',support[2]);
  const retry=' You can retry the same saved submission; do not create another copy.';
  if(value.endsWith(retry))return localizedError(value.slice(0,-retry.length))+' '+t(retry.trim());
  const failed=value.match(/^Request failed \((\d{3})\)\.$/);
  if(failed)return t('Request failed ({0}).',failed[1]);
  if(/(?:fetch|network|timeout|timed out|aborted)/i.test(value))return t('Connection interrupted. Your report is still saved. Check your connection and try again.');
  return t('Something went wrong. Your report is still saved. Error details: {0}',value);
}
export function logWarning(text) {
  const omitted=text.match(/^([^:]+): incomplete or unsupported lines omitted \((\d+)\)\.$/);
  if(omitted)return t('{0}: incomplete or unsupported lines omitted ({1}).',omitted[1],omitted[2]);
  const missing=text.match(/^([^:]+): could not copy the complete retained log\.$/);
  return missing?t('{0}: could not copy the complete retained log.',missing[1]):t(text);
}
if(globalThis.window)Object.defineProperty(window,'KFPSReportLanguage',{value:Object.freeze({current:language})});
