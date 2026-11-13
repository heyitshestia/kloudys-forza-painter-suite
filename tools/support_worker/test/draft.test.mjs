import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeDraft} from '../public/draft.mjs';
import {normalizeReport} from '../public/protocol.mjs';
import {logMetadata} from './log-fixture.mjs';

const report=extra=>({schema:'kfps-support-report/1',id:crypto.randomUUID(),feature:'Editor',description:'',title:'',expected:'',technical:{app:{version:'3.2.3'},unknown:'not allowed'},private_logs:logMetadata,...extra});
test('unfinished drafts preserve text and bounded context without becoming sendable',()=>{
  for(const description of ['', 'lag', '  ', 'a']){
    const value=normalizeDraft(report({description,include_technical:false}));
    assert.equal(value.description,description);assert.equal(value.title,'');assert.equal(value.include_technical,false);
    assert.equal(value.technical.app.version,'3.2.3');assert(!value.technical.unknown);assert.deepEqual(value.private_logs,logMetadata);
    assert.deepEqual(normalizeDraft(value),value);assert.throws(()=>normalizeReport(value),/briefly describe/);
  }
});
test('draft parsing retains privacy filtering, format checks and attachment validation',()=>{
  const value=normalizeDraft(report({description:'lag\npassword=hunter2',title:'C:\\private\\art.png',expected:'me@example.com'}));
  assert(!value.description.includes('hunter2'));assert(!value.title.includes('private'));assert(!value.expected.includes('@'));
  for(const change of [{id:'bad'},{schema:'bad'},{feature:'bad'},{private_logs:{...logMetadata,sha256:'bad'},include_technical:false}])assert.throws(()=>normalizeDraft(report(change)));
});
test('only send-time normalization strips opted-out private context',()=>{
  const draft=normalizeDraft(report({description:'A complete report',include_technical:false}));
  const sent=normalizeReport(draft);assert.deepEqual(sent.technical,{});assert(!sent.private_logs);
  assert.equal(draft.technical.app.version,'3.2.3');assert.deepEqual(draft.private_logs,logMetadata);
});
