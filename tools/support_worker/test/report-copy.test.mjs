import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {copy,reportText} from '../public/report-copy.mjs';
import {korean} from '../public/report-ko.mjs';
import {t,setLanguage,language,localizedError,logWarning} from '../public/report-locale.mjs';

test('automatic logging and privacy text have matching nonempty English/Korean entries',()=>{
  assert.deepEqual(Object.keys(copy.en).sort(),Object.keys(copy.ko).sort());
  for(const [key,en] of Object.entries(copy.en)){
    assert(en.trim());assert(copy.ko[key].trim());assert.notEqual(copy.ko[key],en);
    assert.equal(reportText(key,'ko-KR'),copy.ko[key]);assert.equal(reportText(key,'de-DE'),en);
  }
  const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
  for(const [,key] of html.matchAll(/data-report-copy="([^"]+)"/g))assert(copy.en[key],key);
  assert.match(html,/Hestia Cummings &lt;hestia\.cummings@yandex\.com&gt;/);
  assert(!html.includes('Add a saved KFPS report or restore its logs'));
  assert.match(html,/<section id="report-privacy"/);
  assert.match(copy.en.automaticSend,/never silently sends only a summary/);
  assert.match(copy.en.noLogs,/Sending is blocked/);
});

test('all marked form text and accessibility labels have Korean translations',()=>{
  for(const file of ['index.html','native-auth.html']){
    const html=readFileSync(new URL('../public/'+file,import.meta.url),'utf8');
    for(const [,source] of html.matchAll(/\bdata-i18n(?:\s[^>]*)?>([^<]+)</g))assert(Object.hasOwn(korean,source),source);
    for(const [,source] of html.matchAll(/data-i18n-(?:placeholder|aria-label|title)="([^"]+)"/g))assert(Object.hasOwn(korean,source),source);
  }
  for(const [key,value] of Object.entries(korean)){
    assert(value.trim(),key);
    assert.deepEqual((key.match(/\{\d+\}/g)||[]).sort(),(value.match(/\{\d+\}/g)||[]).sort(),key);
  }
});

test('manual language, automatic display-language precedence and safe interpolation',()=>{
  const saved=globalThis.KFPSReportSystemLanguage;
  try{
    globalThis.KFPSReportSystemLanguage='ko';setLanguage('auto');assert.equal(language(),'ko');
    assert.equal(t('Signed in as {0}','<User>'),'<User> 님으로 로그인했습니다');
    assert.match(logWarning('desktop.log: incomplete or unsupported lines omitted (7).'),/7개/);
    assert.match(localizedError('Request failed (503).'),/503/);
    assert.match(localizedError('unrecognized synthetic failure'),/오류 정보/);
    assert.equal(setLanguage('unexpected'),false);assert.equal(language(),'ko');
    setLanguage('en');assert.equal(t('Send report'),'Send report');
    globalThis.KFPSReportSystemLanguage='en';setLanguage('auto');assert.equal(language(),'en');
  }finally{globalThis.KFPSReportSystemLanguage=saved;setLanguage('auto');}
});
