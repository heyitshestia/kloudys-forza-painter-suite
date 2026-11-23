import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {studioTourSteps} from '../src/web/studio-tour.mjs';
import en from '../src/web/locales/en.mjs';
import ko from '../src/web/locales/ko.mjs';
import ja from '../src/web/locales/ja.mjs';

const messages=JSON.parse(fs.readFileSync(new URL('../src/web/locales/messages.json',import.meta.url),'utf8'));
const html=fs.readFileSync(new URL('../src/web/index.html',import.meta.url),'utf8');
const exportContract='Existing template paint and material records are kept; edited artwork is replaced. Studio body-part selections are not written to the export. Game acceptance remains unverified.';
const resetContract='Initial component configuration restored. Game save files were not changed.';
const controls=['Tour','Livery Studio tour','Close tour','Previous step','Next','Done','Step {0} of {1}',
  'Finish or cancel the current edit or operation before starting the tour.'];
const tokens=value=>value.match(/\{\d+\}/g)?.sort()||[];

test('quick tour follows the workflow from choosing a car to installing a separate design',()=>{
  assert.deepEqual(studioTourSteps.map(step=>step.id),['car','import','transform','inspection','parts','save','export','install']);
  assert(Object.isFrozen(studioTourSteps));
  for(const step of studioTourSteps){
    assert(Object.isFrozen(step));assert.match(step.selector,/^[#.][\w-]+$/);
    assert(step.title&&step.body);
    assert(step.body.split(/\s+/).length<=40,'Tour steps should fit a quick read');
  }
});
for(const [language,pack,index] of [['en',en,-1],['ko',ko,0],['ja',ja,1]]){
  test(`tour controls, steps and verified export contract match the ${language} catalogue`,()=>{
    for(const key of [...controls,...studioTourSteps.flatMap(step=>[step.title,step.body]),exportContract,resetContract]){
      assert(Object.hasOwn(messages,key),key);assert(Object.hasOwn(pack,key),key);
      assert.equal(pack[key],index<0?key:messages[key][index]);
      if(index>=0)assert.notEqual(pack[key],key);
      assert.deepEqual(tokens(pack[key]),tokens(key));
    }
  });
}
test('experimental confirmation states only the verified preservation contract',()=>{
  const confirmation=html.match(/<dialog id="confirmExperiment"[\s\S]*?<\/dialog>/)?.[0];
  assert(confirmation?.includes(exportContract));
  assert(!confirmation.includes('existing tuning and body-kit data are preserved'));
  assert(!/parsed|rendered|previewed.*finish/i.test(confirmation));
  const editor=fs.readFileSync(new URL('../src/web/livery-editor.mjs',import.meta.url),'utf8');
  assert(editor.includes(resetContract));assert(!editor.includes('Template tuning/body-kit data remain unchanged.'));
});
