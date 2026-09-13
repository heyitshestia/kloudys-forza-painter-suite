import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {normalizeEditor} from '../public/editor-diagnostics.mjs';
import {normalizeReport, publicSummary} from '../public/protocol.mjs';

const legacyEditor = () => ({schema:'kfps-editor-diagnostics/1', native:{rssBytes:123456},
  page:{page:'a'.repeat(32),seq:7,metrics:{frameMax:280},state:{layers:2401},recovery:{browserOk:true},events:[]},
  recent:[{kind:'long-task',action:'rotate',duration:280}], installed_assets:{'editor.js':'b'.repeat(64)},
  logging:{written:20,failed:false},age_seconds:5,version:'3.1.77'});
const draft = editor => ({schema:'kfps-support-report/1', id:'a987cb48-c013-41e5-a7a1-8e921bc94950',
  created_at:'2026-09-13T10:00:00Z',source:'kfps',feature:'Editor',title:'Synthetic editor issue',
  description:'Synthetic report, never submitted live.',technical:{editor}});

test('old editor context gains no empty runtime field and keeps its byte-stable shape', () => {
  const old = legacyEditor();
  const normalized = normalizeEditor(old);
  assert.deepEqual(normalized, old);
  const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
  assert.equal(hash(normalized), hash(old));
  for (const editor_runtime of [undefined, {}, null, {python:'private/path',bits:-1}]) {
    assert.deepEqual(normalizeEditor({...old,editor_runtime}),old);
  }
});

test('an older normalized report is unchanged when it is reviewed or retried again', () => {
  const old = normalizeReport(draft(legacyEditor()));
  delete old.technical.editor.editor_runtime;
  assert.deepEqual(normalizeReport(old), old);
  assert.equal(JSON.stringify(normalizeReport(old)), JSON.stringify(old));
});

test('expanded causal context survives repeated review while private text stays excluded', () => {
  const ids = {documentId:1,operationId:2,commitId:3,commandId:4,inputId:5,historyId:6,
    pageId:'c'.repeat(32),requestId:'a987cb48-c013-41e5-a7a1-8e921bc94950'};
  const runtime = {status:'verified',python:'3.12.10',bits:64,qt:'6.11.1',webengine:'6.11.1',
    chromium:'140.0.7339.225',pyside:'6.11.1',baseline:'d'.repeat(64),files:9000,bytes:940000000,verification_ms:500};
  const editor = {...legacyEditor(), editor_runtime:{...runtime,token:'DO_NOT_SEND',path:'C:/private'},
    recent:[{kind:'commit',action:'rotate',...ids}, {kind:'checkpoint',state:'saved',...ids},
      {kind:'job',job:'saveProject',state:'finished',workerDuration:80,...ids}],
    page:{...legacyEditor().page,state:{layers:2401,cachePixels:1234,cacheCount:2401,queueDepth:2,...ids,
      message:'DO_NOT_SEND',shapes:[{type:123}]} }};
  const result = normalizeReport(draft(editor));
  assert.deepEqual(result.technical.editor.editor_runtime,runtime);
  assert.deepEqual(result.technical.editor.recent,editor.recent);
  for (const [key,value] of Object.entries(ids)) assert.equal(result.technical.editor.page.state[key],value);
  assert.equal(result.technical.editor.page.state.cachePixels,1234);
  assert.deepEqual(normalizeReport(result),result);
  assert(!JSON.stringify(result).includes('DO_NOT_SEND'));
  const summary = publicSummary(result,{name:'Synthetic reporter'});
  for (const value of ['cachePixels','chromium','workerDuration','requestId','2401']) assert(!summary.includes(value));
});
