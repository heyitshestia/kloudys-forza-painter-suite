"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "regression-customization-compat.js"), "utf8");
const name = "Customization IME fixture";
const fixture = {format:"kloudy_fabric_editor_project_v1",name,shapes:[{type:1048677,data:[0,0,.4,.4,0,0,0],color:[11,22,33,255]}]};
const clone = value => JSON.parse(JSON.stringify(value));

function helper(name) {
  const start = source.indexOf(`  async function ${name}(`);
  assert.ok(start >= 0, `Missing tested workflow helper ${name}`);
  const end = source.indexOf("\n  }", start);
  assert.ok(end > start);
  return source.slice(start, end + 4);
}

function harness({exists = true, corruptSave = false, corruptLoad = false, staleLoad = false, recoveredUnsaved = false,
  recoveryOpen = false, tipOpen = '', wrongRecoveryName = false, wrongRecoveryShapes = false,
  corruptRecovery = false, staleRecovery = false, pendingVerification = false,
  settlesBeforePicker = false, pickerError = false, wrongConfirmation = false, badReceipt = false,
  wrongReceiptTarget = false, missingReceipt = false, stuckPicker = false, unsafeReplacement = false,
  staleAssociation = false, dirtyAfterLoad = false, confirmationAfterLoad = false,
  saveError = false, savedRecoveryDirty = false, skipsConfirmation = false} = {}) {
  let disk = clone(fixture), canvas = clone(fixture.shapes), fileExists = exists, opened = false, prompt = "";
  let associated = null;
  const events = [];
  const filename = path.join("fixture-profile", "projects", name + ".fabric-project.json");
  const digest = value => require('node:crypto').createHash('sha256').update(value).digest('hex');
  const receipt = () => missingReceipt ? null : ({target_id:(wrongReceiptTarget?'Other':name)+'.fabric-project.json',
    fingerprint:badReceipt?'0'.repeat(64):digest(JSON.stringify(disk))});
  const translate = (text,value) => text.replace('{0}',value);
  const nodes = Object.fromEntries(['projectBrowserDialog','confirmationDialog','messageDialog'].map(id=>[id,{open:false}]));
  nodes.confirmationDialogTitle = {textContent:wrongConfirmation?'Unrelated action':'Unsaved editor changes'};
  nodes.confirmationDialogBody = {textContent:translate('Opening {0} replaces the current workspace. Save the project first if these changes should be kept.',name)};
  nodes.confirmationDialogConfirm = {textContent:'Open Anyway'};
  const context = {
    assert, path, hash:digest, fixtureName:name, fixtureFile:filename,
    report:{steps:[]},
    fs:{existsSync:() => fileExists, readFileSync:() => JSON.stringify(disk)},
    currentProjectName:name, documentGeneration:0, projectSaveInProgress:false, documentDirty:recoveredUnsaved, recoveryRestoreDepth:0,
    editorCommands:{busy:false}, snapshotShapes:() => clone(canvas),
    KfpsI18n:{t:translate},
    editorProjects:{expected:()=>associated},
    document:{getElementById:id=>nodes[id],querySelectorAll:()=>Object.entries(nodes).filter(([,n])=>n.open).map(([id])=>({id}))},
    isDocumentDirty:() => context.documentDirty,
    recoveryAutosavePayload:recoveryOpen ? {shapes:wrongRecoveryShapes ? [] : clone(fixture.shapes),
      editor_session:{project_name:wrongRecoveryName ? 'Unrelated fixture' : name,saved:true,receipt:receipt()}} : null,
  };
  const write = () => {
    if(saveError){nodes.messageDialog.open=true;return;}
    if (corruptSave) disk.shapes = [];
    else disk.shapes = clone(canvas);
    fileExists = true;
    associated = receipt();
    context.documentDirty = false;
    events.push("write");
  };
  context.command = async id => {
    events.push(id);
    if(id === 'loadProject') {
      nodes.projectBrowserDialog.open = true;
      if(settlesBeforePicker)context.documentDirty = false;
    }
    if (id === "saveProject") {
      assert.ok(opened, "Ordinary save needs a real project-picker load first");
      write();
    }
  };
  context.page = {
    evaluate: async (fn,arg) => {context.evalArg=arg;return vm.runInContext(`(${fn.toString()})(evalArg)`, sandbox);},
    waitForFunction: async (fn, arg) => {
      context.waitArg = arg;
      const result = vm.runInContext(`(${fn.toString()})(waitArg)`, sandbox);
      assert.ok(result, "Wait condition must be true");
      return {jsonValue:async()=>clone(result),dispose:async()=>{}};
    },
    getByText: value => { assert.equal(value, name); return {}; },
    locator: selector => ({
      filter() { return this; },
      async evaluateAll(fn) {return fn(Object.entries(nodes).filter(([,n])=>n.open).map(([id])=>({id})));},
      async textContent() {return nodes[selector.slice(1)].textContent;},
      async evaluate(fn) {
        return fn(nodes[selector.slice(1)] || {open:selector === '#autosaveRecoveryDialog' ? recoveryOpen : selector === '#' + tipOpen});
      },
      async click() {
        events.push(selector);
        if (selector === '#recoverAutosave') {
          assert.equal(recoveryOpen,true);
          recoveryOpen = false;
          if (!staleRecovery) context.documentGeneration += 1;
          canvas = corruptRecovery ? [] : clone(context.recoveryAutosavePayload.shapes);
          if (!pendingVerification) {
            context.recoveryAutosavePayload = null;
            associated = receipt();
            context.documentDirty = savedRecoveryDirty;
          }
        }
        if(selector === '#selectProjectEntry' && pickerError) {nodes.messageDialog.open=true;return;}
        if(selector === '#selectProjectEntry' && context.documentDirty && !skipsConfirmation) {
          nodes.confirmationDialog.open=true;
          if(unsafeReplacement)context.documentGeneration++;
          return;
        }
        if (selector === "#selectProjectEntry" || selector === "#confirmationDialogConfirm") {
          assert.ok(fileExists);
          opened = true;
          if (!staleLoad) context.documentGeneration += 1;
          context.documentDirty = dirtyAfterLoad;
          canvas = corruptLoad ? [] : clone(disk.shapes);
          associated = staleAssociation ? null : receipt();
          nodes.confirmationDialog.open=confirmationAfterLoad;nodes.projectBrowserDialog.open=stuckPicker;
        }
      },
      async waitFor(options) {
        if (selector === '#autosaveRecoveryDialog') {
          assert.equal(options.state,'hidden');
          assert.equal(recoveryOpen,false);
          return;
        }
        assert.equal(selector,"#confirmationDialog");
        assert.equal(options.state,"visible");
        assert.equal(context.documentDirty,true);
        events.push("confirmation-visible");
      },
      async fill(value) { prompt = value; },
      async press(key) {
        assert.equal(key, "Enter");
        assert.equal(prompt, name);
        assert.equal(fileExists, false, "Save As must not overwrite an existing fixture");
        write();
      },
    }),
  };
  const sandbox = vm.createContext(context);
  vm.runInContext(['assertCustomizationReceipt','waitForCustomizationOutcome','reopenCustomizationFixture',
    'saveCustomizationFixture','restoreCustomizationRecovery'].map(helper).join('\n'), sandbox);
  return {events,context,run:code=>vm.runInContext(code,sandbox),edit() {canvas[0].data[0] += 7.25;context.documentDirty=true;}};
}

(async () => {
  const first = harness({exists:false});
  await first.run("saveCustomizationFixture(false)");
  assert.equal(first.events.filter(e=>e === "saveProjectAs").length,1);
  assert.equal(first.events.filter(e=>e === "#selectProjectEntry").length,1);

  const restart = harness();
  await restart.run("reopenCustomizationFixture()");
  restart.edit();
  await restart.run("saveCustomizationFixture(true)");
  assert.equal(restart.events.includes("saveProjectAs"),false);
  assert.equal(restart.events.filter(e=>e === "saveProject").length,1);
  assert.equal(restart.events.filter(e=>e === "#selectProjectEntry").length,2);

  const missing = harness({exists:false});
  await assert.rejects(missing.run("reopenCustomizationFixture()"));
  assert.deepEqual(missing.events,[]);
  const collision = harness();
  await assert.rejects(collision.run("saveCustomizationFixture(false)"));
  assert.deepEqual(collision.events,[]);
  const badSave = harness({exists:false,corruptSave:true});
  await assert.rejects(badSave.run("saveCustomizationFixture(false)"));
  const badLoad = harness({corruptLoad:true});
  await assert.rejects(badLoad.run("reopenCustomizationFixture()"));
  const staleLoad = harness({staleLoad:true});
  await assert.rejects(staleLoad.run("reopenCustomizationFixture()"));
  const recovered = harness({recoveredUnsaved:true});
  await recovered.run("reopenCustomizationFixture()");
  assert.ok(recovered.events.includes("#confirmationDialogConfirm"));

  const noOffer = harness();
  await noOffer.run('restoreCustomizationRecovery()');
  assert.deepEqual(noOffer.events,[]);
  const offer = harness({recoveryOpen:true});
  await offer.run('restoreCustomizationRecovery()');
  assert.deepEqual(offer.events,['#recoverAutosave']);
  assert.equal(offer.context.report.recovery.fixtureVerified,true);
  await offer.run('reopenCustomizationFixture()');
  offer.edit();
  await offer.run('saveCustomizationFixture(true)');
  assert.ok(offer.events.indexOf('#recoverAutosave') < offer.events.indexOf('loadProject'));
  for (const tipOpen of ['startupHelpDialog','languageNoticeDialog','editorUpdateDialog','projectSharingDialog']) {
    const unexpected = harness({recoveryOpen:true,tipOpen});
    await assert.rejects(unexpected.run('restoreCustomizationRecovery()'));
    assert.deepEqual(unexpected.events,[],'Never dismiss a first-time modal to make restart pass');
  }
  for (const invalid of [{wrongRecoveryName:true},{wrongRecoveryShapes:true},{corruptRecovery:true},{staleRecovery:true}]) {
    const broken = harness({recoveryOpen:true,...invalid});
    await assert.rejects(broken.run('restoreCustomizationRecovery()'));
  }
  const receiptPending = harness({recoveryOpen:true,pendingVerification:true});
  await assert.rejects(receiptPending.run('restoreCustomizationRecovery()'));
  const settled = harness({recoveredUnsaved:true,settlesBeforePicker:true});
  await settled.run('reopenCustomizationFixture()');
  assert.equal(settled.events.includes('#confirmationDialogConfirm'),false);
  for (const invalid of [{pickerError:true},{wrongConfirmation:true,recoveredUnsaved:true},{badReceipt:true}]) {
    const rejected = harness(invalid);
    await assert.rejects(rejected.run('reopenCustomizationFixture()'));
    assert.equal(rejected.events.includes('#confirmationDialogConfirm'),false);
  }
  for (const invalid of [{wrongReceiptTarget:true},{missingReceipt:true},{stuckPicker:true},{staleAssociation:true},
    {dirtyAfterLoad:true},{confirmationAfterLoad:true},{unsafeReplacement:true,recoveredUnsaved:true}]) {
    const rejected = harness(invalid);
    await assert.rejects(rejected.run('reopenCustomizationFixture()'));
    assert.equal(rejected.events.includes('#confirmationDialogConfirm'),false);
  }
  const skipped = harness({recoveredUnsaved:true,skipsConfirmation:true});
  await assert.rejects(skipped.run('reopenCustomizationFixture()'), /must not be replaced without confirmation/);
  for (const invalid of [{savedRecoveryDirty:true},{badReceipt:true},{missingReceipt:true}]) {
    const rejected = harness({recoveryOpen:true,...invalid});
    await assert.rejects(rejected.run('restoreCustomizationRecovery()'));
  }
  const failedSave = harness({saveError:true});
  await failedSave.run('reopenCustomizationFixture()');failedSave.edit();
  await assert.rejects(failedSave.run('saveCustomizationFixture(true)'));
  assert.equal(failedSave.events.filter(e=>e==='#selectProjectEntry').length,1,'Failed save must not proceed to reopen');

  const restartBranch = source.slice(source.indexOf("saved=JSON.parse(fs.readFileSync(stateFile"),source.indexOf("assert.equal((await uiState()).language,'ja')"));
  assert.match(restartBranch,/await reopenCustomizationFixture\(\)/);
  assert.ok(restartBranch.indexOf('await restoreCustomizationRecovery()') >= 0
    && restartBranch.indexOf('await restoreCustomizationRecovery()') < restartBranch.indexOf('await reopenCustomizationFixture()'));
  assert.match(source,/if \(!restart\) await loadPayload/);
  assert.match(source,/await saveCustomizationFixture\(options\.customizationRestart === true\)/);
  console.log(JSON.stringify({passed:true,cases:39,browserLaunches:0,productWrites:0}));
})().catch(error => {console.error(error);process.exitCode=1;});
