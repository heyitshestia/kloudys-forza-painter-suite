const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const modulePath = path.join(__dirname, '../editor-workspace.js');
const searchSource = file => fs.readFileSync(file,'utf8').replace(/\r\n/g,'\n').split('// BEGIN FIXED WEB COMMAND SEARCH')[1].split('// END FIXED WEB COMMAND SEARCH')[0];

test('fixed command bridge reuses owners and rejects stale page/document IDs', () => {
  const context=vm.createContext({module:{exports:{}}});vm.runInContext(searchSource(modulePath),context);
  const {createBridge} = context.module.exports;
  let revision = 'document-1', busy = '', disabled = false, calls = 0;
  const make = () => createBridge({owner:'editor', pageId:String(Math.random()),
    revision:()=>revision, blocked:()=>busy,
    commands:()=>[{key:'saveProject',label:'Save project',description:'Editable',shortcut:'Alt+S',enabled:!disabled,reason:disabled?'Unavailable':''}],
    dispatch:key=>{assert.equal(key,'saveProject');calls++;}});
  const api=make(), first=api.list();
  assert.deepEqual(Object.keys(api).sort(),['activity','execute','list']);
  assert.equal(api.activity().running,false);
  assert.equal(first.commands[0].shortcut,'Alt+S');
  assert.equal(api.execute('saveProject').ok,false);
  assert.equal(api.execute('constructor',first.token).ok,false);
  assert.equal(api.execute(first.commands[0].id,first.token).ok,true);
  disabled=true;assert.equal(api.execute(first.commands[0].id,first.token).ok,false);
  disabled=false;busy='modal';assert.equal(api.execute(first.commands[0].id,first.token).ok,false);
  busy='';revision='document-2';assert.equal(api.execute(first.commands[0].id,first.token).error,'stale-context');
  const second=api.list();assert.notEqual(second.token,first.token);
  assert.equal(make().execute(second.commands[0].id,second.token).ok,false);
  assert.equal(calls,1);
});

test('both isolated web servers carry identical bounded search implementation', () => {
  assert.equal(searchSource(modulePath),searchSource(path.join(__dirname,'../../../tools/livery-studio/src/web/livery-editor.mjs')));
});

test('output wording distinguishes editable save, artwork, groups and unverified ZIP', () => {
  const editor=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
  const studio=fs.readFileSync(path.join(__dirname,'../../../tools/livery-studio/src/web/index.html'),'utf8');
  assert.match(editor,/id="saveProject"[^>]*>Save project</);
  assert.match(editor,/id="exportJson"[^>]*>Export artwork</);
  assert.match(editor,/id="exportDestinationSummary"/);
  assert.match(editor,/Live-memory transfers remain flat/);
  assert.match(studio,/id="outputSummary"/);
  assert.match(studio,/It is not installed automatically/);
});
