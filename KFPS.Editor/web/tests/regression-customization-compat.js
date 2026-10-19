async (page, options = {}) => {
  const assert = require('node:assert/strict');
  const cp = require('node:child_process'), crypto = require('node:crypto');
  const root = process.env.KFPS_TEST_APP_ROOT || path.resolve(__dirname, '../../..');
  const referenceRoot = process.env.KFPS_TEST_REFERENCE_ROOT || root;
  const info = fs.existsSync(path.join(output, 'process.json')) ? JSON.parse(fs.readFileSync(path.join(output, 'process.json'))) : null;
  const profile = info?.profile || path.join(output, 'profile');
  const prefsFile = path.join(profile, 'preferences.json');
  const stateFile = path.join(profile, 'customization-compat-state.json');
  const hash = value => crypto.createHash('sha256').update(value).digest('hex');
  const readPrefs = () => JSON.parse(fs.readFileSync(prefsFile, 'utf8'));
  const report = {passed:false, steps:[], layouts:[], limitations:[]};
  const idle = () => page.waitForFunction(() => window.KfpsDesktop?.ready && !editorCommands.busy && !projectSaveInProgress);
  const flush = () => page.evaluate(() => KfpsEditorPreferences.flush());
  const command = async (id, menu) => {
    if (!await page.locator('#'+id).isVisible()) await page.locator(`#workspace${menu}Menu`).click();
    await page.locator('#'+id).click();
  };
  const fixtureName = 'Customization IME fixture';
  const fixtureFile = path.join(profile, 'projects', fixtureName + '.fabric-project.json');
  async function assertCustomizationReceipt(fileBytes) {
    const receipt = await page.evaluate(name => editorProjects.expected(name), fixtureName);
    assert.equal(receipt?.target_id, fixtureName + '.fabric-project.json', 'Receipt must belong to the actual fixture');
    assert.equal(receipt?.fingerprint, hash(fileBytes), 'Receipt must match the actual saved bytes');
    return receipt;
  }
  async function waitForCustomizationOutcome(generation, allowConfirmation) {
    const handle = await page.waitForFunction(({name, generation}) => {
      const ids = [...document.querySelectorAll('dialog[open]')].map(node => node.id);
      const settled = currentProjectName === name && documentGeneration > generation
        && !editorCommands.busy && !projectSaveInProgress && !recoveryRestoreDepth
        && recoveryAutosavePayload === null && !documentDirty && !isDocumentDirty();
      if (!ids.some(id => id !== 'projectBrowserDialog') && !(settled && ids.length === 0)) return false;
      const text = id => document.getElementById(id)?.textContent;
      return {ids, settled, generation:documentGeneration, dirty:documentDirty,
        title:text('confirmationDialogTitle'), body:text('confirmationDialogBody'), confirm:text('confirmationDialogConfirm'),
        expectedTitle:KfpsI18n.t('Unsaved editor changes'), expectedConfirm:KfpsI18n.t('Open Anyway'),
        expectedBody:KfpsI18n.t('Opening {0} replaces the current workspace. Save the project first if these changes should be kept.', name)};
    }, {name:fixtureName, generation});
    let result;
    try { result = await handle.jsonValue(); } finally { await handle.dispose(); }
    if (result.ids.length) {
      assert.equal(allowConfirmation, true, 'Unexpected modal while awaiting completed project load: ' + JSON.stringify(result));
      assert.deepEqual([...result.ids].sort(), ['confirmationDialog','projectBrowserDialog'], 'Only the project replacement confirmation is permitted');
      assert.equal(result.generation, generation, 'Confirmation must precede replacement');
      assert.equal(result.dirty, true, 'Replacement confirmation must protect unsaved work');
      assert.equal(result.title, result.expectedTitle);
      assert.equal(result.body, result.expectedBody);
      assert.equal(result.confirm, result.expectedConfirm);
      return 'confirmation';
    }
    assert.equal(result.settled, true, 'A missing modal is not proof that loading succeeded');
    return 'loaded';
  }
  async function restoreCustomizationRecovery() {
    for (const id of ['startupHelpDialog','languageNoticeDialog','editorUpdateDialog','projectSharingDialog']) {
      assert.equal(await page.locator('#' + id).evaluate(node => node.open), false,
        `First-time dialog ${id} must remain closed in the migrated profile`);
    }
    const offered = await page.locator('#autosaveRecoveryDialog').evaluate(node => node.open);
    report.recovery = {offered, restoredViaUI:false};
    if (!offered) return;
    const fileBefore = fs.readFileSync(fixtureFile, 'utf8');
    const expected = JSON.parse(fileBefore);
    assert.equal(expected.format, 'kloudy_fabric_editor_project_v1');
    assert.equal(expected.name, fixtureName);
    assert.equal(expected.shapes.length, 1);
    const recovery = JSON.parse(JSON.stringify(await page.evaluate(() => recoveryAutosavePayload)));
    assert.equal(recovery?.editor_session?.project_name, fixtureName, 'Recovery must identify the saved test fixture');
    assert.deepEqual(recovery.shapes, expected.shapes, 'Recovery offer must contain the actual saved fixture');
    const generation = await page.evaluate(() => documentGeneration);
    await page.locator('#recoverAutosave').click();
    await page.locator('#autosaveRecoveryDialog').waitFor({state:'hidden'});
    await page.waitForFunction(({name, generation}) => currentProjectName === name && documentGeneration > generation
      && !editorCommands.busy && !projectSaveInProgress && !recoveryRestoreDepth
      && recoveryAutosavePayload === null, {name:fixtureName, generation});
    assert.deepEqual(JSON.parse(JSON.stringify(await page.evaluate(() => snapshotShapes()))), expected.shapes,
      'Restore UI must recover the expected fixture before project-picker loading');
    assert.equal(fs.readFileSync(fixtureFile, 'utf8'), fileBefore, 'Recovery must not rewrite the saved project');
    const state = await page.evaluate(() => ({dirty:documentDirty, computedDirty:isDocumentDirty()}));
    assert.equal(state.dirty, state.computedDirty, 'Recovery dirty state must be finalized');
    if (recovery.editor_session?.saved === true) {
      await assertCustomizationReceipt(fileBefore);
      assert.equal(state.dirty, false, 'This saved fixture has a valid receipt and no edits or unavailable reference');
    }
    report.recovery = {offered:true, restoredViaUI:true, fixtureVerified:true, finalized:true,
      dirty:state.dirty, shapes:expected.shapes.length};
    report.steps.push('Legitimate recovery offer restored through its UI; recovered fixture verified before project-picker loading');
  }
  async function reopenCustomizationFixture() {
    assert.ok(fs.existsSync(fixtureFile), 'Restart must use the actual saved customization project');
    const fileBefore = fs.readFileSync(fixtureFile, 'utf8');
    const expected = JSON.parse(fileBefore);
    assert.equal(expected.format, 'kloudy_fabric_editor_project_v1');
    assert.equal(expected.name, fixtureName);
    assert.equal(expected.shapes.length, 1);
    const generation = await page.evaluate(() => documentGeneration);
    await command('loadProject', 'File');
    await page.locator('.projectBrowserEntry').filter({has:page.getByText(fixtureName,{exact:true})}).click();
    const beforeSelect = await page.evaluate(() => ({dirty:documentDirty, computedDirty:isDocumentDirty(),
      generation:documentGeneration, recoveryPending:recoveryAutosavePayload !== null,
      busy:editorCommands.busy || projectSaveInProgress || !!recoveryRestoreDepth}));
    assert.equal(beforeSelect.generation, generation, 'No unrelated load may replace the workspace while selecting a project');
    assert.equal(beforeSelect.recoveryPending, false, 'Recovery must finish before the picker replacement decision');
    assert.equal(beforeSelect.busy, false);
    assert.equal(beforeSelect.dirty, beforeSelect.computedDirty, 'Picker must start from a settled dirty state');
    await page.locator('#selectProjectEntry').click();
    const outcome = await waitForCustomizationOutcome(generation, true);
    if (beforeSelect.dirty) assert.equal(outcome, 'confirmation', 'Settled unsaved work must not be replaced without confirmation');
    if (outcome === 'confirmation') {
      await page.locator('#confirmationDialogConfirm').click();
      await waitForCustomizationOutcome(generation, false);
    }
    await assertCustomizationReceipt(fileBefore);
    assert.deepEqual(JSON.parse(JSON.stringify(await page.evaluate(() => snapshotShapes()))), expected.shapes,
      'Project-picker reopening must retain the actual saved shapes');
    assert.equal(fs.readFileSync(fixtureFile, 'utf8'), fileBefore, 'Reopening must not rewrite the saved fixture');
    (report.fixtureLoads ||= []).push({dirtyBeforeSelect:beforeSelect.dirty,
      replacementConfirmed:outcome === 'confirmation', receiptVerified:true});
    return expected;
  }
  async function saveCustomizationFixture(restart) {
    const expectedShapes = JSON.parse(JSON.stringify(await page.evaluate(() => snapshotShapes())));
    if (restart) {
      assert.ok(fs.existsSync(fixtureFile), 'Never replace a missing restart fixture with a new project');
      await assertCustomizationReceipt(fs.readFileSync(fixtureFile, 'utf8'));
      await command('saveProject', 'File');
    } else {
      assert.equal(fs.existsSync(fixtureFile), false, 'First-run Save As requires a fresh fixture name');
      await command('saveProjectAs', 'File');
      await page.locator('#textPromptInput').fill(fixtureName);
      await page.locator('#textPromptInput').press('Enter');
    }
    await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty());
    const writtenBytes = fs.readFileSync(fixtureFile, 'utf8');
    await assertCustomizationReceipt(writtenBytes);
    const written = JSON.parse(writtenBytes);
    assert.deepEqual(written.shapes, expectedShapes, 'Actual saved file must contain the edited shapes');
    await reopenCustomizationFixture();
    report.savedFixture = {name:fixtureName, restart, diskVerified:true, pickerReopened:true, shapes:written.shapes.length};
  }
  const themeValue = () => page.evaluate(() => editorTheme.themeFieldCurrentValues()['--accent']);
  const uiState = () => page.evaluate(() => ({language:KfpsI18n.language, lang:document.documentElement.lang,
    theme:editorSettings.getItem('kloudyFabricTheme'), shortcut:shortcutFor('colorSlot1'),
    favoriteColors, favorites:[...favorites], dock:readDockState(),
    font:getComputedStyle(document.body).fontFamily, reuseFont:reuseLastFontSize,
    textFont:editorSettings.getItem('kloudyFabricTextVinylFont')}));
  let version = 'new', route = null, saved;
  page.setDefaultTimeout(20000);
  try {
    if (!options.customizationRestart) {
      const commit = '33de8f5589519c6e9320617eb3c148fb602ab5ff';
      const get = file => cp.execFileSync('git', ['show', `${commit}:${file}`], {cwd: referenceRoot,windowsHide:true,maxBuffer:16*1024*1024});
      const manifest = JSON.parse(get('KFPS.Editor/manifest.json'));
      const assets = new Map(manifest.web.map(entry=>[entry.path,get(`${manifest.web_root}/${entry.path}`)]));
      route = async request => {
        const pathname = new URL(request.request().url()).pathname;
        const file = pathname.split('/tools/fabric-editor/')[1] || 'index.html';
        if (version !== 'old' || !assets.has(file)) return request.continue();
        return request.fulfill({body:assets.get(file),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':file.endsWith('.html')?'text/html':'application/json'});
      };
      await page.route('**/tools/fabric-editor/**', route);
      await flush();
      const prefs = readPrefs();
      prefs.fixture_unknown = {owner:'synthetic',nested:[1,'日本語','한국어']};
      prefs.settings.fixture_font = {family:'Fixture font sentinel',future:true};
      prefs.settings.kloudyFabricReuseLastFontSize = 'true';
      prefs.settings.kloudyFabricTextVinylFont = '1';
      prefs.settings.kloudyFabricFavoriteColors = JSON.stringify([[11,22,33,255],[80,90,100,120]]);
      prefs.settings.kloudyFabricFavorites = JSON.stringify([1048677,1048678]);
      prefs.settings.kloudyFabricDockState = JSON.stringify({hidden:false,width:410,fixture_future:{keep:'unchanged'}});
      const theme = {id:'fixture-compat-theme',name:'Fixture Theme 日本語',base:'dark',
        values:{'--accent':'#36a7b8','--text':'#fafafa','--panel':'#20262a','--font-family':'Fixture font sentinel'},
        fixture_unknown:{font:'unchanged',future:[1,2]}};
      fs.mkdirSync(path.join(profile,'themes'),{recursive:true});
      const themeFile = path.join(profile,'themes',theme.id+'.json');
      fs.writeFileSync(themeFile,JSON.stringify(theme,null,2));
      prefs.theme = theme.id;
      prefs.settings.kloudyFabricTheme = theme.id;
      prefs.settings.kloudyFabricLanguage = 'en';
      fs.writeFileSync(prefsFile,JSON.stringify(prefs,null,2));
      version='old'; await page.reload(); await idle();
      await page.waitForFunction(()=>!document.querySelector('dialog[open]'));
      assert.equal(await themeValue(),'#36a7b8');
      await command('shortcutsBtn','Help');
      await page.locator('[data-shortcut-action="colorSlot1"]').click();
      await page.keyboard.press('Control+Shift+9');
      await page.locator('#closeShortcuts').click();
      await flush();
      const old = await uiState();
      assert.equal(old.shortcut,'Ctrl+Shift+9');
      assert.equal(old.reuseFont,true);
      assert.deepEqual(readPrefs().fixture_unknown,prefs.fixture_unknown);
      saved={themeFile,themeHash:hash(fs.readFileSync(themeFile)),unknown:prefs.fixture_unknown,
        fontField:prefs.settings.fixture_font,old,oldEditorSha:hash(assets.get('editor.js'))};
      report.steps.push('Pinned old editor loads synthetic custom theme and saves modifier shortcut');

      version='new'; await page.reload(); await idle();
      await page.waitForFunction(()=>!document.querySelector('dialog[open]'));
      const current=await uiState();
      for (const key of ['theme','shortcut','favoriteColors','favorites','reuseFont','textFont']) assert.deepEqual(current[key],old[key],key);
      assert.deepEqual(current.dock.fixture_future,{keep:'unchanged'});
      assert.equal(await themeValue(),'#36a7b8');
      report.steps.push('Old to new theme, shortcut, favorites, supported font settings and opaque dock fields preserved');

      await command('adjustTheme','View');
      await page.locator('#theme-accent').fill('#d86a91');
      await page.locator('#theme-accent').dispatchEvent('input');
      assert.equal(await themeValue(),'#d86a91');
      await page.locator('#closeThemeAdjust').click();
      assert.equal(await themeValue(),'#36a7b8');
      await command('adjustTheme','View');
      await page.locator('#theme-accent').fill('#d86a91');
      await page.locator('#theme-accent').dispatchEvent('input');
      await page.locator('#themeAdjustName').fill('Compatibility 日本語');
      await page.locator('#saveThemeAdjust').click();
      await page.waitForFunction(()=>!document.querySelector('#themeAdjustDialog').open);
      await flush();
      saved.selectedTheme=(await uiState()).theme;
      assert.notEqual(saved.selectedTheme,'fixture-compat-theme');
      assert.equal(await themeValue(),'#d86a91');
      assert.equal(hash(fs.readFileSync(themeFile)),saved.themeHash);
      report.steps.push('Theme editor preview/cancel/save creates a new file and preserves the original');

      saved.fontBeforeJapanese=(await uiState()).font;
      await page.locator('#editorLanguageSelect').selectOption('ja');
      await flush();
      await page.reload(); await idle();
      await page.waitForFunction(()=>!document.querySelector('dialog[open]'));
      assert.equal((await uiState()).font,saved.fontBeforeJapanese,'Language must not override the existing UI font stack');
      saved.expected=await uiState();
      saved.hostPid=info?.pid || null;
      fs.writeFileSync(stateFile,JSON.stringify(saved,null,2));
      report.steps.push('Actual language selector saves Japanese without modifying the theme or font');
    } else {
      saved=JSON.parse(fs.readFileSync(stateFile,'utf8'));
      if (info?.pid && saved.hostPid) assert.notEqual(info.pid,saved.hostPid,'Use a fresh host process');
      await idle();
      const reopened=await uiState();
      for (const key of ['language','lang','theme','shortcut','favoriteColors','favorites','font','reuseFont','textFont']) assert.deepEqual(reopened[key],saved.expected[key],key);
      assert.equal(await themeValue(),'#d86a91');
      await restoreCustomizationRecovery();
      report.steps.push('Fresh host restores Japanese, theme, shortcuts and supported font settings without first-time dialogs');
      await reopenCustomizationFixture();
      report.steps.push('Restart reopens the actual saved customization project through the project picker');
    }

    assert.equal((await uiState()).language,'ja');
    assert.equal((await uiState()).lang,'ja');
    const session=await page.context().newCDPSession(page);
    let catalogScript;
    session.on('Debugger.scriptParsed',entry=>{if(entry.url.split('?')[0].endsWith('/locales/ja.js'))catalogScript=entry.scriptId;});
    try {
      await session.send('Debugger.enable');
      assert.ok(catalogScript,'Japanese catalog must actually execute');
      const loaded=await session.send('Debugger.getScriptSource',{scriptId:catalogScript});
      report.japaneseCatalogSha256=hash(loaded.scriptSource);
      assert.equal(report.japaneseCatalogSha256,hash(fs.readFileSync(path.join(root,'KFPS.Editor/web/locales/ja.js'))));
    } finally {await session.send('Debugger.disable');await session.detach();}
    const translated=await page.evaluate(()=>({label:KfpsI18n.t('File'),expected:KfpsEditorLocales.ja.messages.File,
      visible:document.querySelector('#workspaceFileMenu').textContent}));
    assert.ok(/[\u3040-\u30ff\u4e00-\u9fff]/.test(translated.label));
    assert.equal(translated.label,translated.expected);
    assert.ok(translated.visible.includes(translated.label));
    await command('shortcutsBtn','Help');
    const capture=page.locator('[data-shortcut-action="colorSlot1"]');
    for (const event of [{key:'あ',code:'Digit9',ctrlKey:true,shiftKey:true,isComposing:true},
      {key:'Process',keyCode:229,isComposing:true},{key:'한',isComposing:true}]) {
      await capture.focus(); await capture.dispatchEvent('keydown',{...event,bubbles:true,cancelable:true});
      assert.equal(await page.evaluate(()=>shortcutFor('colorSlot1')),'Ctrl+Shift+9','IME composition must not replace shortcut');
    }
    await capture.blur();
    assert.equal(await capture.inputValue(),'Ctrl+Shift+9');
    await page.locator('#closeShortcuts').click();
    await page.evaluate(async restart=>{
      if (!restart) await loadPayload({shapes:[{type:1048677,data:[0,0,.4,.4,0,0,0],color:[220,40,50,255]}]});
      selectObjects(vinylObjects(),'customization shortcut fixture');
      if (restart) {
        // Keep the project-picker receipt and make a real persisted change.
        const shape = vinylObjects()[0];
        shape.set({left:shape.left + .25});
        shape.setCoords();
        pushHistory('customization restart fixture edit');
        applyEditorColor([220,40,50,255], 'customization shortcut fixture');
      }
      document.activeElement?.blur();
    }, options.customizationRestart === true);
    await page.keyboard.press('Control+Shift+9');
    assert.deepEqual(await page.evaluate(()=>objectToShape(vinylObjects()[0]).color),[11,22,33,255]);
    const artworkBeforeIme=await page.evaluate(()=>JSON.stringify(snapshotShapes()));
    await page.evaluate(()=>{
      for(const key of ['あ','한','Process']) document.dispatchEvent(new KeyboardEvent('keydown',{
        key,code:'Digit9',ctrlKey:true,shiftKey:true,isComposing:true,bubbles:true,cancelable:true}));
      const altGr=new KeyboardEvent('keydown',{key:'9',ctrlKey:true,altKey:true,shiftKey:true,bubbles:true,cancelable:true});
      Object.defineProperty(altGr,'getModifierState',{value:key=>key==='AltGraph'});
      document.dispatchEvent(altGr);
    });
    assert.equal(await page.evaluate(()=>JSON.stringify(snapshotShapes())),artworkBeforeIme);
    await saveCustomizationFixture(options.customizationRestart === true);
    report.steps.push('Migrated modifier shortcut executes; Japanese/Korean composition and AltGr do not alter artwork');
    for (const size of [{width:1760,height:1040},{width:1280,height:800},{width:900,height:640}]) {
      await page.setViewportSize(size);
      await command('shortcutsBtn','Help');
      const geometry=await page.locator('#shortcutsDialog').evaluate(node=>{const b=node.getBoundingClientRect();return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,scroll:node.scrollWidth,client:node.clientWidth,w:innerWidth,h:innerHeight};});
      assert.ok(geometry.left>=0&&geometry.right<=geometry.w+1&&geometry.top>=0&&geometry.bottom<=geometry.h+1&&geometry.scroll<=geometry.client+2,JSON.stringify(geometry));
      await page.screenshot({path:path.join(output,`ja-shortcuts-${size.width}.png`)});
      await page.locator('#closeShortcuts').click();
      report.layouts.push({...size,geometry});
    }
    await flush();
    const finalPrefs=readPrefs();
    assert.deepEqual(finalPrefs.fixture_unknown,saved.unknown);
    assert.deepEqual(finalPrefs.settings.fixture_font,saved.fontField);
    assert.equal(hash(fs.readFileSync(saved.themeFile)),saved.themeHash);
    assert.ok(fs.existsSync(path.join(profile,'startup-help-confirmed.json')));
    report.steps.push('Japanese rendering, IME protection and three viewport sizes; original file and unrelated JSON fields unchanged');
    report.limitations.push('Original editor has 33 supported color-theme keys, not a configurable UI-font field. Opaque font metadata is preserved but never newly applied; supported text-vinyl font settings and computed UI font stack are checked.');
    report.limitations.push('Historical web code executes against the current isolated host; physical Japanese IME input and display-driver rendering are not exercised by injected/headless input.');
    report.passed=true;
    return report;
  } finally {
    if (route) await page.unroute('**/tools/fabric-editor/**',route);
    fs.writeFileSync(path.join(output,'customization-compat.json'),JSON.stringify(report,null,2));
  }
}
