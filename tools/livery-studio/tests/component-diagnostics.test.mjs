import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {componentCatalog,validateVehicleParts} from '../src/web/component-model.mjs';
import {errorText,setLanguage} from '../src/web/i18n.mjs';
import en from '../src/web/locales/en.mjs';
import ko from '../src/web/locales/ko.mjs';
import ja from '../src/web/locales/ja.mjs';

const key='Unavailable component selection: {0}.';
const expected={en:key,ko:'선택한 부품을 사용할 수 없습니다: {0}.',ja:'選択したパーツは利用できません: {0}。'};
const messages=JSON.parse(fs.readFileSync(new URL('../src/web/locales/messages.json',import.meta.url),'utf8'));
const catalog=componentCatalog(['CarBody','RearWing'].map((part_type,index)=>({
  part_type,id:index+1,stock:true,supported:true,car_body_id:-1,
})));
const tokens=value=>value.match(/\{\d+\}/g)?.sort()||[];

for(const [language,pack,index] of [['en',en,-1],['ko',ko,0],['ja',ja,1]]){
  test(`component diagnostic matches canonical ${language} catalog`,()=>{
    assert.deepEqual(Object.keys(pack),Object.keys(messages));
    assert(Object.hasOwn(messages,key));
    assert.equal(pack[key],expected[language]);
    assert.equal(pack[key],index<0?key:messages[key][index]);
    assert.deepEqual(tokens(pack[key]),tokens(key));
  });
  test(`actual unavailable body and wing validation errors translate in ${language}`,()=>{
    setLanguage(language);
    try{
      for(const part of ['CarBody','RearWing']){
        const value={[part]:999};const before=structuredClone(value);
        assert.throws(()=>validateVehicleParts(value,catalog),error=>{
          assert.equal(error.message,key.replace('{0}',part));
          assert.equal(errorText(error),expected[language].replace('{0}',part));return true;
        });
        assert.deepEqual(value,before);
      }
    }finally{setLanguage('en');}
  });
}
test('component names remain opaque, including placeholder and markup text',()=>{
  const name='<svg data-id="{1}"> $&';
  for(const language of ['ko','ja']){
    setLanguage(language);
    assert.equal(errorText(key.replace('{0}',()=>name)),expected[language].replace('{0}',()=>name));
  }
  setLanguage('en');
});
test('unmatched diagnostics stay intact and existing option translation still works',()=>{
  for(const [language,pack] of [['ko',ko],['ja',ja]]){
    setLanguage(language);
    for(const message of ['Unavailable component selection: RearWing','Prefix Unavailable component selection: RearWing.',
      'Unavailable component selection: RearWing. Extra','Unrecognized component diagnostic'])assert.equal(errorText(message),message);
    assert.equal(errorText('Unavailable component option: RearWing'),pack['Unavailable component option: {0}'].replace('{0}','RearWing'));
  }
  setLanguage('en');
});
