async (page, options = {}) => {
  const assert = require('node:assert/strict'), cp = require('node:child_process');
  const crypto = require('node:crypto');
  const root = process.env.KFPS_TEST_APP_ROOT || path.resolve(__dirname, '../../..');
  const referenceRoot = process.env.KFPS_TEST_REFERENCE_ROOT || root;
  const commit = '33de8f5589519c6e9320617eb3c148fb602ab5ff';
  const oldManifest = JSON.parse(cp.execFileSync('git', ['show', `${commit}:KFPS.Editor/manifest.json`], {cwd: referenceRoot, windowsHide: true, encoding: 'utf8'}));
  const hash = value => crypto.createHash('sha256').update(value).digest('hex');
  const oldAssets = new Map(oldManifest.web.map(item => [item.path,
    cp.execFileSync('git', ['show', `${commit}:${oldManifest.web_root}/${item.path}`], {cwd: referenceRoot, windowsHide: true, maxBuffer: 16 * 1024 * 1024})]));
  const frozen = fs.readFileSync(path.join(referenceRoot, 'runtime/test-runs/frozen-baseline/editor.js'));
  assert.equal(hash(frozen), hash(oldAssets.get('editor.js')), 'Use the verified original baseline, not another work-in-progress');
  const processInfo = fs.existsSync(path.join(output, 'process.json')) ? JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8')) : null;
  const profile = processInfo?.profile || path.join(output, 'profile');
  const exportsRoot = processInfo?.exportRoot || path.join(output, 'exports');
  const projectOnly = options.projectOnly === true;
  const report = {passed: false, commit, projectOnly, nativeExportVerified: !projectOnly, versions: [], directions: [], precision: 'native transform values are serialized to six decimal places', limitations: []};
  const checkpoint = stage => {
    report.stage = stage;
    fs.writeFileSync(path.join(output, 'cross-version-progress.json'), JSON.stringify(report, null, 2));
    console.log('Cross-version checkpoint: ' + stage);
  };
  let version = 'new';
  const route = async request => {
    const pathname = new URL(request.request().url()).pathname;
    const relative = pathname.split('/tools/fabric-editor/')[1] || 'index.html';
    if (version !== 'old' || !oldAssets.has(relative)) return request.continue();
    const contentType = relative.endsWith('.js') ? 'text/javascript' : relative.endsWith('.html') ? 'text/html' : relative.endsWith('.css') ? 'text/css' : 'application/json';
    return request.fulfill({body: oldAssets.get(relative), contentType});
  };
  const idle = () => page.waitForFunction(() => window.KfpsDesktop?.ready && !editorCommands.busy && !projectSaveInProgress && !recoveryRestoreDepth);
  const command = async (menu, id) => {
    if (!await page.locator('#'+id).isVisible()) await page.locator(`#workspace${menu}Menu`).click();
    await page.locator('#'+id).click();
  };
  const save = async name => {
    await command('File', 'saveProjectAs');
    await page.locator('#textPromptInput').fill(name);
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty());
    const filename = path.join(profile, 'projects', name + '.fabric-project.json');
    assert.ok(fs.existsSync(filename));
    return {filename, project: JSON.parse(fs.readFileSync(filename, 'utf8'))};
  };
  const exportNative = async name => {
    await page.locator('#exportJson').click();
    await page.waitForFunction(() => !exportSaveInProgress && !editorCommands.busy);
    const files = fs.readdirSync(exportsRoot, {recursive:true}).filter(file => file.endsWith('.json'));
    const filename = files.map(file => path.join(exportsRoot, file)).find(file => path.basename(file).startsWith(name + '.'));
    assert.ok(filename, `Actual native JSON export missing for ${name}`);
    const entry = await page.evaluate(() => selectedJsonBrowserEntry());
    assert.ok(entry && entry.name === path.basename(filename), 'Export receipt must select the actual browser entry');
    if (options.expectScopedExports) assert.ok(entry.id.startsWith('@exports/'));
    assert.equal(entry.layers, 3000);
    return {filename, payload: JSON.parse(fs.readFileSync(filename, 'utf8')), entry};
  };
  const canonical = payload => ({shapes: payload.shapes, guides: payload.editor_guides,
    collapsed: payload.editor_collapsed_groups, reference: payload.editor_source_overlay});
  async function switchVersion(next) {
    checkpoint('switch-start-' + next);
    await page.evaluate(async () => { await clearAutosave(); await KfpsEditorPreferences.flush(); });
    version = next;
    await page.reload(); await idle();
    await page.waitForFunction(() => !document.querySelector('dialog[open]'));
    const session = await page.context().newCDPSession(page), scripts = new Map();
    session.on('Debugger.scriptParsed', entry => { if (entry.url.split('?')[0].endsWith('/editor.js')) scripts.set('editor', entry.scriptId); });
    await session.send('Debugger.enable');
    const loaded = await session.send('Debugger.getScriptSource', {scriptId: scripts.get('editor')});
    const expected = next === 'old' ? oldAssets.get('editor.js') : fs.readFileSync(path.join(root, 'KFPS.Editor/web/editor.js'));
    assert.equal(hash(loaded.scriptSource), hash(expected), 'Actual executing editor must match the selected version');
    report.versions.push({version: next, editor_sha256: hash(expected)});
    await session.send('Debugger.disable'); await session.detach();
    checkpoint('switch-ready-' + next);
  }
  await page.route('**/tools/fabric-editor/**', route);
  page.setDefaultTimeout(45000);
  try {
    for (const [origin, target] of [['old', 'new'], ['new', 'old']]) {
      await switchVersion(origin);
      await page.evaluate(async () => {
        const shapes = Array.from({length:3000}, (_, i) => ({type:1048677 + i % 3,
          data:[i % 60 * 25 - 750 + .1234567, Math.floor(i / 60) * 25 - 625 + .7654321,
            (i % 11 === 0 ? -1 : 1) * (.12 + i % 7 * .01), .18 + i % 5 * .01, i % 360 + .1234567, (i % 9 - 4) * .03125, i === 1 ? 1 : 0, 123.456789],
          color:[i % 256, (i * 7) % 256, (i * 13) % 256, 40 + i % 216],
          editor_id:`cross-${i}`, editor_locked:i===3, editor_hidden:i===4,
          ...(i < 3 ? {editor_group_id:'inner',editor_group_name:'Inner',editor_group_path:[{id:'outer',name:'Outer'},{id:'inner',name:'Inner'}]} : {}),
          future_fixture: 'unsupported-unknown-shape-property'}));
        await loadProjectPayload({format:'kloudy_fabric_editor_project_v1',name:'Cross-version fixture',shapes,
          editor_collapsed_groups:['outer'], future_fixture:'unsupported-unknown-project-property'}, 'Cross-version fixture');
        const image=document.createElement('canvas'); image.width=96; image.height=64;
        const ctx=image.getContext('2d');ctx.fillStyle='#58b4ca';ctx.fillRect(0,0,96,64);ctx.fillStyle='#f07a41';ctx.fillRect(5,5,20,15);
        await editorReference.loadOverlayImageFromUrl(image.toDataURL(), 'cross-reference.png');
        editorReference.image.set({left:13.25,top:-7.5,angle:11,skewX:7,scaleX:1.2,scaleY:.8,opacity:.42});
        document.querySelector('#overlayOpacity').value = 42;
        document.querySelector('#overlayOpacity').dispatchEvent(new Event('input',{bubbles:true}));
        editorReference.setSizeLocked(true);
        pushHistory('cross-version fixture');
      });
      await idle();
      checkpoint(origin + '-fixture-loaded');
      if (projectOnly && origin === 'new') {
        const before = await page.evaluate(() => {
          const target = vinylObjects().find(o=>o.kloudy.editor_id==='cross-5');
          selectObjects([target], 'installed numeric edit');
          if (typeof activateDockPanel === 'function') activateDockPanel('propertiesPane');
          return JSON.stringify(snapshotShapes());
        });
        const input = await page.evaluate(() => {
          const field = document.querySelector('#xInput');
          return {exists: !!field, disabled: field?.disabled, value: field?.value};
        });
        assert.ok(input.exists && !input.disabled, 'Numeric edit field must exist and be enabled');
        const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
        await h.type(page, '#xInput', '144.25');
        await page.locator('#xInput').press('Enter');
        const edited = await page.evaluate(()=>JSON.stringify(snapshotShapes()));
        assert.notEqual(edited, before, 'Actual numeric input must edit the 3000-shape project');
        await command('Edit', 'undoBtn'); await idle();
        assert.equal(await page.evaluate(()=>JSON.stringify(snapshotShapes())), before);
        await command('Edit', 'redoBtn'); await idle();
        assert.equal(await page.evaluate(()=>JSON.stringify(snapshotShapes())), edited);
        report.installedNumericEditUndoRedo = true;
      }
      const name = `Cross ${origin} to ${target}`;
      const original = await save(name), portable = projectOnly ? null : await exportNative(name);
      checkpoint(origin + '-saved-exported');
      assert.equal(original.project.shapes.length, 3000);
      if (portable) assert.equal(portable.payload.shapes.length, 3000);
      assert.equal(original.project.editor_source_overlay.controls.size_locked, true);
      assert.equal(original.project.shapes.filter(s=>s.editor_group_path?.length===2).length, 3);
      if (portable) {
        assert.equal(portable.payload.shapes.filter(s=>s.mask).length, 1);
        assert.ok(portable.payload.shapes.every(s=>!Object.keys(s).some(key=>key.startsWith('editor_'))));
      }
      await switchVersion(target);
      if (projectOnly) {
        await command('File', 'loadProject');
        await page.locator('.projectBrowserEntry').filter({has:page.getByText(name,{exact:true})}).click();
        await page.locator('#selectProjectEntry').click();
        await page.waitForFunction(()=>vinylObjects().length===3000&&!recoveryRestoreDepth&&!isDocumentDirty());
      } else {
        await page.evaluate(async payload => { await loadProjectPayload(payload, 'Cross-version received'); }, original.project);
      }
      checkpoint(target + '-project-reopened');
      const received = await save(name + ' received');
      assert.deepEqual(canonical(received.project), canonical(original.project), `${origin}->${target}: editable project changed`);
      // Compare the JSON wire format: JSON has no distinct negative-zero value.
      if (portable) {
        const beforePortable = await page.evaluate(() => JSON.parse(JSON.stringify(vinylObjects().map(o=>objectToShape(o,{includeEditorMeta:false})))));
        assert.deepEqual(beforePortable, portable.payload.shapes, `${origin}->${target}: portable serialization changed`);
        await page.locator('#jsonInput').setInputFiles(portable.filename);
        await idle();
        const importedNative = await page.evaluate(() => JSON.parse(JSON.stringify(vinylObjects().map(o=>objectToShape(o,{includeEditorMeta:false})))));
        assert.deepEqual(importedNative, portable.payload.shapes, `${origin}->${target}: native JSON import changed geometry/color/mask`);
        await save(name + ' native reopened');
        if (options.expectScopedExports) {
          await command('File', 'openJsonBrowser');
          await page.locator('#jsonBrowserSource').selectOption('editor');
          await page.waitForFunction(() => !jsonBrowserState.loading);
          await page.locator('.jsonBrowserCard').filter({has:page.getByText(name,{exact:true})}).click();
          await page.locator('.jsonBrowserEntry').filter({has:page.getByText(portable.entry.name,{exact:true})}).click();
          await page.waitForFunction(() => {
            const image = document.querySelector('#jsonBrowserPreviewImage');
            return image && !image.hidden && image.complete && image.naturalWidth > 0;
          });
          assert.equal(await page.evaluate(()=>selectedJsonBrowserEntry().id), portable.entry.id);
          await page.locator('#selectJsonBrowserEntry').click();
          await page.locator('#jsonBrowserDialog').waitFor({state:'hidden'});
          await idle();
          assert.deepEqual(await page.evaluate(() => JSON.parse(JSON.stringify(vinylObjects().map(o=>objectToShape(o,{includeEditorMeta:false}))))), portable.payload.shapes);
          await save(name + ' browser reopened');
        }
      }
      report.directions.push({origin,target,layers:3000,exactProject:true,exactNative:portable?true:null,projectPicker:projectOnly,scopedBrowserPreviewAndLoad:!!(portable&&options.expectScopedExports),nestedGroups:3,masks:1,referenceAndSizeLock:true,
        unknownProjectRetained:Object.hasOwn(original.project,'future_fixture'),unknownShapeRetained:Object.hasOwn(original.project.shapes[0],'future_fixture')});
      fs.writeFileSync(path.join(output, `${origin}-project.json`), JSON.stringify(original.project));
      if (portable) fs.writeFileSync(path.join(output, `${origin}-native.json`), JSON.stringify(portable.payload));
    }
    report.limitations.push('Unknown arbitrary project/shape keys are not serialized by either editor; supported editor metadata and native data tail values are preserved. Original input files are not rewritten.');
    report.limitations.push('The historical editor web assets execute against the isolated current host/server. This is actual serializer/importer compatibility, not a full historical runtime qualification.');
    if (projectOnly) report.limitations.push('Explicit project-only mode: native JSON export/import is not tested in this invocation. Use the default full suite to qualify export.');
    await switchVersion('new');
    report.passed = true;
    return report;
  } finally {
    await page.unroute('**/tools/fabric-editor/**', route);
    fs.writeFileSync(path.join(output, 'cross-version-projects.json'), JSON.stringify(report,null,2));
  }
}
