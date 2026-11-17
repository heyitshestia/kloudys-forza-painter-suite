async (page, options = {}) => {
  const assert = { ...require('node:assert/strict') };
  const { isDeepStrictEqual } = require('node:util');
  // Node's full diff for a dense, mismatched shape array can exhaust the driver heap.
  const digest = value => crypto.createHash('sha256').update(JSON.stringify(value) ?? 'undefined').digest('hex');
  const persisted = value => value === undefined ? value : JSON.parse(JSON.stringify(value));
  assert.deepEqual = (actual, expected, message) => {
    const equal = isDeepStrictEqual(persisted(actual), persisted(expected));
    if (!equal) fs.writeFileSync(path.join(output, 'assertion-difference.json'), JSON.stringify({ message, actual, expected }, null, 2));
    assert.ok(equal, `${message || 'Values differ'} (actual ${digest(actual)}, expected ${digest(expected)})`);
  };
  const layers = 1493, checks = [];
  page.setDefaultTimeout(20000);
  const phase = name => console.log(JSON.stringify({ recoveryPhase: name }));
  const timeout = 60000;
  const inside = (root, target) => {
    const relative = path.relative(root, target);
    return relative && relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative);
  };
  const runs = fs.realpathSync(path.resolve(__dirname, '../../../runtime/test-runs'));
  const runOutput = fs.realpathSync(output);
  assert.ok(inside(runs, runOutput), 'Evidence must remain inside runtime/test-runs');
  const processInfo = JSON.parse(fs.readFileSync(path.join(runOutput, 'process.json'), 'utf8'));
  assert.equal(typeof processInfo.profile, 'string', 'process.json must identify the isolated profile');
  const profile = fs.realpathSync(processInfo.profile);
  assert.ok(inside(runs, profile), 'Refusing to use a profile outside runtime/test-runs');
  const url = new URL(page.url());
  assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname), 'A local test host is required');
  assert.ok(url.pathname.includes('fabric-editor'), 'The actual editor page is required');
  assert.ok(!url.searchParams.has('harness') && !url.searchParams.has('textVinylHarness'),
    'Recovery must not be bypassed by harness mode');
  if (options.recoveryPhase === 'restart') {
    assert.equal(options.preserveStartupNotices, true,
      'Restart requires preserveStartupNotices:true; the runner otherwise closes recovery dialogs before this test');
  } else assert.ok(!options.recoveryPhase, 'Only recoveryPhase:restart is supported');

  const snapshot = () => page.evaluate(() => ({
    shapes: snapshotShapes(), reference: editorReference.sourceOverlayProjectState(),
    guides: savedGuideState(), collapsed: collapsedLayerGroupIds(), name: currentProjectName,
    dirty: documentDirty, computedDirty: isDocumentDirty(), receipt: editorProjects.association,
    historyClean: currentHistoryState() === savedHistoryState,
    overlayClean: overlayRevision === savedOverlayRevision,
    referenceLoaded: Boolean(editorReference.image), pageId: KfpsEditorDiagnostics.snapshot().page,
  }));
  const exact = (actual, expected, label) => {
    for (const key of ['shapes', 'reference', 'guides', 'collapsed', 'name']) {
      assert.deepEqual(actual[key], expected[key], label + ': ' + key);
    }
    assert.equal(actual.shapes.length, layers, label + ': layer count');
    assert.equal(actual.referenceLoaded, true, label + ': decoded reference');
  };
  const clean = (actual, expected, label) => {
    exact(actual, expected, label);
    assert.equal(actual.dirty, false, label + ': dirty flag');
    assert.equal(actual.computedDirty, false, label + ': computed dirty flag');
    assert.equal(actual.historyClean && actual.overlayClean, true, label + ': saved baselines');
    assert.deepEqual(actual.receipt, expected.receipt, label + ': receipt');
    assert.ok(actual.receipt?.fingerprint, label + ': confirmed receipt');
  };
  const checkpoint = () => page.evaluate(async () => {
    await flushPendingAutosave();
    if (editorRecovery.backupPromise) await editorRecovery.backupPromise;
    const selected = await readAutosavePayload();
    const durable = await editorPersistence.request('readRecovery');
    return { selected, durable: durable.payload, highestRevision: durable.highestRevision };
  });
  const checkCheckpoint = (value, expected, saved) => {
    for (const [store, payload] of [['selected', value.selected], ['durable', value.durable]]) {
      assert.ok(payload, store + ': checkpoint missing');
      assert.deepEqual(payload.shapes, expected.shapes, store + ': exact shapes');
      assert.deepEqual(payload.editor_source_overlay, expected.reference, store + ': exact reference');
      assert.deepEqual(payload.editor_guides, expected.guides, store + ': exact guides');
      assert.deepEqual(payload.editor_collapsed_groups, expected.collapsed, store + ': exact groups');
      assert.equal(payload.editor_session.saved, saved, store + ': saved classification');
      assert.equal(payload.editor_session.project_name, expected.name, store + ': project name');
      assert.deepEqual(payload.editor_session.receipt, expected.receipt, store + ': receipt');
    }
  };
  const noRecoveryDialog = async label => {
    assert.equal(await page.locator('#autosaveRecoveryDialog').isVisible(), false, label + ': recovery dialog');
    assert.equal(await page.evaluate(() => Boolean(window.__recoveryStartupObserved?.opened)), false,
      label + ': recovery dialog briefly opened');
  };
  const startupReady = () => page.waitForFunction(() => window.KfpsDesktop?.ready && startupRecoveryHandled
    && !recoveryRestoreDepth && !editorCommands.busy && !projectSaveInProgress, null, { timeout });
  const command = async id => {
    if (!await page.locator('#' + id).isVisible()) await page.locator('#workspaceFileMenu').click();
    await page.locator('#' + id).click();
  };
  const save = async () => {
    const previous = await page.evaluate(() => editorProjects.association?.fingerprint || null);
    await command('saveProject');
    await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty()
      && Boolean(editorProjects.association), null, { timeout });
    const result = await snapshot();
    checkCheckpoint(await checkpoint(), result, true);
    assert.equal(result.dirty, false, 'UI Save did not clear the dirty flag');
    return { snapshot: result, previousFingerprint: previous };
  };
  const navigate = async saved => {
    const sameUrl = page.url();
    if (saved) await page.reload();
    else {
      // This is deliberate test navigation, not a user close or a project save.
      await page.evaluate(() => {
        if (window.qt?.webChannelTransport) {
          // Qt's hidden runner rejects native beforeunload prompts. Suppress only
          // that prompt after checkpointing; history and saved baselines stay dirty.
          documentDirty = false;
        } else window.__KfpsBrowserCloseAllowed = true;
      });
      await page.goto(sameUrl);
    }
    await startupReady();
    await noRecoveryDialog(saved ? 'Saved automatic startup' : 'Unsaved automatic startup');
  };
  const stageCheckpoint = async payload => {
    await page.evaluate(async payload => {
      writeAutosavePayload(payload);
      await flushPendingAutosave();
      if (editorRecovery.backupPromise) await editorRecovery.backupPromise;
    }, payload);
  };

  await page.waitForFunction(() => window.KfpsDesktop?.ready, null, { timeout });
  await noRecoveryDialog('Initial page');
  // Do not use the runner's blanket dialog dismissal: a recovery prompt is a failure.
  await page.evaluate(async () => {
    if (document.getElementById('autosaveRecoveryDialog').open) throw Error('Unexpected initial recovery dialog');
    if (startupProjectId() || startupJsonId() || startupBrowseMode()) throw Error('Use ordinary session startup, not an explicit file');
    editorSettings.setItem(PROJECT_SHARING_ACK_KEY, PROJECT_SHARING_NOTICE_VERSION);
    editorSettings.setItem(LANGUAGE_NOTICE_ACK_KEY, '1');
    editorSettings.setItem(EDITOR_UPDATE_ACK_KEY, EDITOR_UPDATE_NOTICE_VERSION);
    await KfpsEditorPreferences.flush();
    await writeStartupHelpConfirmed();
    document.getElementById('startupHelpDialog')?.close();
  });
  await startupReady();
  await noRecoveryDialog('Acknowledged initial tips');

  if (options.recoveryPhase === 'restart') {
    assert.equal(typeof options.recoveryExpected, 'string', 'Restart requires recoveryExpected');
    const expectedPath = fs.realpathSync(options.recoveryExpected);
    assert.ok(inside(runs, expectedPath), 'Restart evidence must come from runtime/test-runs');
    const expected = JSON.parse(fs.readFileSync(expectedPath, 'utf8'));
    assert.equal(expected.schema, 'kfps-recovery-startup-v1');
    assert.equal(fs.realpathSync(expected.profile), profile, 'Restart must reuse the original isolated profile');
    const actual = await snapshot();
    clean(actual, expected.snapshot, 'Full process restart');
    assert.notEqual(actual.pageId, expected.snapshot.pageId, 'Restart reused the original renderer');
    checkCheckpoint(await checkpoint(), actual, true);
    assert.equal(await page.evaluate(receipt => editorProjects.verify(receipt), actual.receipt), true);
    await page.screenshot({ path: path.join(runOutput, 'recovery-restarted.png') });
    return { passed: true, phase: 'restart', layers, exact: true, clean: true, expectedPath };
  }

  // Observe transient prompts too; never install a recovery-click adapter.
  await page.addInitScript(() => {
    const observed = window.__recoveryStartupObserved = { opened: false };
    new MutationObserver(records => {
      if (document.querySelector('#autosaveRecoveryDialog[open]') || records.some(record =>
        record.target.id === 'autosaveRecoveryDialog' && record.attributeName === 'open'
        && record.oldValue !== null)) observed.opened = true;
    }).observe(document, { subtree: true, childList: true, attributes: true,
      attributeFilter: ['open'], attributeOldValue: true });
  });
  const name = 'Recovery startup ' + Date.now();
  const projects = path.join(profile, 'projects');
  const projectPath = path.join(projects, name + '.fabric-project.json');
  assert.equal(fs.existsSync(projectPath), false, 'Synthetic project name already exists');
  await page.evaluate(async ({ layers, name }) => {
    const bitmap = document.createElement('canvas');
    bitmap.width = 32; bitmap.height = 24;
    const context = bitmap.getContext('2d');
    context.fillStyle = '#217eaa'; context.fillRect(0, 0, 32, 24);
    context.fillStyle = '#f0546b'; context.fillRect(3, 5, 11, 13);
    const shapes = Array.from({ length: layers }, (_, index) => ({
      type: 1048677, color: [40 + index % 150, 80 + index % 100, 210, 255],
      data: [(index % 47) * 12 - 276, Math.floor(index / 47) * 12 - 180, .075, .075, 0, 0, 0],
      editor_id: 'recovery-layer-' + index, shape_name: 'Recovery layer ' + index,
      editor_group_path: [{ id: 'recovery-root', name: 'Recovery group' },
        { id: 'recovery-group-' + Math.floor(index / 100), name: 'Batch ' + Math.floor(index / 100) }],
    }));
    validateStrictInputShapes(shapes);
    await loadProjectPayload({ name, shapes, editor_collapsed_groups: ['recovery-group-2'],
      editor_guides: { guides: [{ id: 'recovery-guide', x1: -210, y1: -100, x2: 210, y2: 100 }],
        gridEnabled: true, gridSize: 25, guidesVisible: true },
      editor_source_overlay: { kind: 'image', file_name: 'synthetic-recovery.png',
        data_url: bitmap.toDataURL('image/png'), transform: { opacity: .6 },
        controls: { opacity_percent: 60, scale_percent: 100, size_locked: false, layer_mode: 'below' } },
    }, name);
  }, { layers, name });
  phase('fixture-loaded');
  let saved = (await save()).snapshot;
  phase('fixture-saved');
  assert.ok(saved.shapes.every(shape => shape.editor_group_path?.length === 2), 'Fixture lost nested groups');
  assert.equal(saved.guides.guides.length, 1, 'Fixture guide missing');
  assert.equal(saved.collapsed.length, 1, 'Fixture collapsed group missing');
  assert.ok(inside(profile, fs.realpathSync(projects)), 'Project directory escaped the isolated profile');
  assert.equal(fs.realpathSync(projectPath), path.resolve(projectPath), 'Synthetic project must not be a link');
  const disk = JSON.parse(fs.readFileSync(projectPath, 'utf8'));
  assert.deepEqual(disk.shapes, saved.shapes, 'UI Save changed disk shapes');
  assert.deepEqual(disk.editor_source_overlay, saved.reference, 'UI Save changed disk reference');
  await navigate(true);
  clean(await snapshot(), saved, 'Saved reload');
  checkCheckpoint(await checkpoint(), saved, true);
  checks.push('1493 grouped shapes, reference and guides: UI save and exact automatic clean reload');
  phase('saved-reload');

  await page.locator('.upper-canvas').click({ position: { x: 8, y: 8 } });
  await page.evaluate(() => selectObjects([vinylObjects()[0]], 'recovery unsaved nudge'));
  await page.keyboard.press('ArrowRight');
  await page.evaluate(() => flushPendingNudgeHistory());
  const unsaved = await snapshot();
  assert.equal(unsaved.dirty && unsaved.computedDirty, true, 'Actual keyboard edit was not dirty');
  assert.notDeepEqual(unsaved.shapes[0], saved.shapes[0], 'Actual keyboard edit did not change a shape');
  assert.deepEqual(unsaved.shapes.slice(1), saved.shapes.slice(1), 'Nudge changed unrelated shapes');
  checkCheckpoint(await checkpoint(), unsaved, false);
  await navigate(false);
  const recoveredUnsaved = await snapshot();
  exact(recoveredUnsaved, unsaved, 'Unsaved reload');
  assert.equal(recoveredUnsaved.dirty && recoveredUnsaved.computedDirty, true, 'Unsaved recovery falsely became saved');
  assert.deepEqual(recoveredUnsaved.receipt, unsaved.receipt, 'Unsaved recovery lost its verified disk target');
  checkCheckpoint(await checkpoint(), recoveredUnsaved, false);
  checks.push('unsaved UI edit: explicit close allowance, same-URL goto, exact dirty recovery');
  phase('unsaved-reload');
  saved = (await save()).snapshot;
  const savedCheckpoint = (await checkpoint()).selected;

  // Mutate only this newly created synthetic project, and restore its exact bytes on every exit.
  const originalBytes = fs.readFileSync(projectPath);
  const renamedPath = projectPath + '.recovery-startup-test-backup';
  assert.equal(fs.existsSync(renamedPath), false, 'Refusing to overwrite a recovery backup');
  for (const fault of ['missing', 'modified']) {
    phase('project-' + fault);
    let renamed = false, modified = false;
    try {
      if (fault === 'missing') { fs.renameSync(projectPath, renamedPath); renamed = true; }
      else {
        const changed = JSON.parse(originalBytes.toString('utf8'));
        changed.shapes[0].color[0] = (changed.shapes[0].color[0] + 19) % 256;
        modified = true;
        fs.writeFileSync(projectPath, JSON.stringify(changed));
      }
      await navigate(true);
      const actual = await snapshot();
      exact(actual, saved, fault + ' project receipt');
      assert.equal(actual.dirty && actual.computedDirty, true, fault + ': falsely clean');
      assert.equal(Boolean(actual.receipt), false, fault + ': stale receipt retained');
      checkCheckpoint(await checkpoint(), actual, false);
      assert.equal(await page.evaluate(receipt => editorProjects.verify(receipt), saved.receipt), false,
        fault + ': invalid receipt verified');
      checks.push(fault + ' disk project: exact recovery remains dirty without a false saved receipt');
    } finally {
      if (renamed) {
        assert.equal(fs.existsSync(projectPath), false, 'Unexpected replacement appeared while project was renamed');
        fs.renameSync(renamedPath, projectPath);
      }
      if (modified) fs.writeFileSync(projectPath, originalBytes);
      assert.ok(fs.readFileSync(projectPath).equals(originalBytes), 'Synthetic project bytes were not restored');
    }
    await stageCheckpoint(savedCheckpoint);
    await navigate(false);
    clean(await snapshot(), saved, fault + ': restored disk and saved checkpoint');
  }

  phase('restore-failures');
  const protectedCheckpoint = await checkpoint();
  const failureMarker = 'Injected recovery startup strict validation failure';
  const callback = await page.evaluate(async marker => {
    const original = validateStrictInputShapes;
    const failures = [];
    validateStrictInputShapes = () => { throw Error(marker); };
    try {
      const result = await recoverAutosavePayload(await readAutosavePayload(), {
        onFailure: message => failures.push(message),
      });
      // Exercise the real automatic caller, not a stubbed false return or a fabricated dialog.
      await maybeShowAutosaveRecovery();
      return { result, failures };
    } finally { validateStrictInputShapes = original; }
  }, failureMarker);
  assert.equal(callback.result, false);
  assert.equal(callback.failures.length, 1, 'Real failure did not call onFailure exactly once');
  assert.ok(callback.failures[0].includes(failureMarker));
  await page.locator('#autosaveRecoveryDialog').waitFor({ state: 'visible', timeout });
  assert.equal(await page.locator('#autosaveRecoveryError').isVisible(), true);
  assert.ok((await page.locator('#autosaveRecoveryError').textContent()).includes(failureMarker));
  assert.deepEqual(await checkpoint(), protectedCheckpoint, 'Automatic failure replaced the checkpoint');
  clean(await snapshot(), saved, 'Automatic failure retained the live document');

  const labels = [];
  const languages = options.recoveryLanguages || ['en', 'ko', 'ja'];
  for (const language of languages) {
    assert.ok(['en', 'ko', 'ja'].includes(language), 'Unsupported recovery label language');
    labels.push(await page.evaluate(async ({ language, failure }) => {
      const originalUrl = location.href, originalLanguage = KfpsI18n.language;
      const next = new URL(originalUrl); next.searchParams.set('lang', language);
      try {
        history.replaceState(null, '', next.href); KfpsI18n.init();
        await showAutosaveRecovery(recoveryAutosavePayload, failure);
        await nextFrame();
        const sources = { autosaveRecoveryTitle: 'Resume Saved Session?',
          autosaveRecoveryHeading: 'Saved Project Verified',
          autosaveRecoveryDescription: 'The project file matches its last confirmed save. This recovery copy can resume that session.',
          recoverAutosave: 'Resume Session' };
        const values = {};
        for (const [id, source] of Object.entries(sources)) {
          const expected = KfpsI18n.t(source), actual = document.getElementById(id).textContent.trim();
          if (actual !== expected || language !== 'en' && expected === source) throw Error(language + ': untranslated ' + id);
          values[id] = actual;
        }
        const error = document.getElementById('autosaveRecoveryError');
        if (error.hidden || error.textContent !== KfpsI18n.t(
          'Restoration did not finish: {0} Your recovery copy has been kept.', failure)) throw Error('Missing localized recovery error');
        return { language, ...values, error: error.textContent };
      } finally {
        history.replaceState(null, '', originalUrl);
        KfpsI18n.init({ getItem: () => originalLanguage });
        await showAutosaveRecovery(recoveryAutosavePayload, failure);
      }
    }, { language, failure: callback.failures[0] }));
  }
  await page.screenshot({ path: path.join(runOutput, 'recovery-automatic-failure.png') });

  await page.evaluate(() => {
    const fault = window.__recoveryStartupBuildFault = { original: makeFabricObject, entered: false, calls: 0 };
    const gate = new Promise(resolve => { fault.release = resolve; });
    makeFabricObject = async function (...args) {
      if (++fault.calls === 1) {
        fault.entered = true;
        await gate;
        throw Error('Injected recovery startup Fabric rejection');
      }
      return fault.original.apply(this, args);
    };
  });
  try {
    await page.locator('#recoverAutosave').click();
    await page.waitForFunction(() => window.__recoveryStartupBuildFault.entered, null, { timeout });
    for (const id of ['recoverAutosave', 'dismissAutosave', 'discardAutosave']) {
      assert.equal(await page.locator('#' + id).isDisabled(), true, id + ': enabled during restore');
    }
    // Native DOM click must also be inert on disabled Keep/Discard controls.
    await page.evaluate(() => {
      document.getElementById('dismissAutosave').click();
      document.getElementById('discardAutosave').click();
    });
    assert.equal(await page.locator('#autosaveRecoveryDialog').isVisible(), true, 'In-flight dialog closed');
    assert.deepEqual(await checkpoint(), protectedCheckpoint, 'In-flight restore changed the checkpoint');
  } finally {
    await page.evaluate(() => {
      const fault = window.__recoveryStartupBuildFault;
      fault.release(); makeFabricObject = fault.original;
    });
  }
  await page.waitForFunction(() => !document.getElementById('recoverAutosave').disabled, null, { timeout });
  assert.equal(await page.locator('#autosaveRecoveryDialog').isVisible(), true, 'Failed retry closed the dialog');
  assert.equal(await page.locator('#autosaveRecoveryError').isVisible(), true, 'Retry error is hidden');
  const retryError = (await page.locator('#autosaveRecoveryError').textContent()).trim();
  assert.ok(retryError && !retryError.includes(failureMarker), 'Manual failure did not refresh the error text');
  for (const id of ['dismissAutosave', 'discardAutosave']) assert.equal(await page.locator('#' + id).isDisabled(), false);
  assert.deepEqual(await checkpoint(), protectedCheckpoint, 'Failed manual restore replaced the checkpoint');
  clean(await snapshot(), saved, 'Failed manual restore retained the live document');
  await page.screenshot({ path: path.join(runOutput, 'recovery-manual-failure.png') });
  await page.locator('#recoverAutosave').click();
  await page.locator('#autosaveRecoveryDialog').waitFor({ state: 'hidden', timeout });
  await startupReady();
  clean(await snapshot(), saved, 'Successful real retry');
  checkCheckpoint(await checkpoint(), saved, true);
  checks.push('real validation/build failures, visible errors, three disabled controls, unchanged checkpoint, successful retry');

  const beforeCancel = await checkpoint();
  const cancellation = await page.evaluate(async () => {
    const original = makeFabricObject, failures = [];
    let supersede = true;
    makeFabricObject = async function (...args) {
      if (supersede) { supersede = false; beginDocumentLoad(); }
      return original.apply(this, args);
    };
    try {
      const result = await recoverAutosavePayload(await readAutosavePayload(), { onFailure: message => failures.push(message) });
      supersede = true;
      await maybeShowAutosaveRecovery();
      await nextFrame();
      return { result, failures, dialogOpen: document.getElementById('autosaveRecoveryDialog').open };
    } finally { makeFabricObject = original; clearBusy(); }
  });
  assert.deepEqual(cancellation, { result: false, failures: [], dialogOpen: false }, 'Cancellation was reported as failure');
  assert.deepEqual(await checkpoint(), beforeCancel, 'Cancellation changed the checkpoint');
  clean(await snapshot(), saved, 'Cancelled recovery retained live document');
  checks.push('superseded real load returns false without onFailure or a new recovery prompt');

  saved = (await save()).snapshot;
  clean(saved, saved, 'Final saved checkpoint');
  const expectedPath = path.join(runOutput, 'recovery-expected.json');
  const expected = { schema: 'kfps-recovery-startup-v1', profile, projectPath, snapshot: saved,
    checkpoint: (await checkpoint()).selected,
    restartOptions: { recoveryPhase: 'restart', recoveryExpected: expectedPath, preserveStartupNotices: true } };
  fs.writeFileSync(expectedPath, JSON.stringify(expected, null, 2));
  assert.deepEqual(JSON.parse(fs.readFileSync(expectedPath, 'utf8')), expected, 'Restart evidence did not reopen exactly');
  const result = { passed: true, layers, checks, labels, expectedPath,
    host: options.browserHost ? 'chrome' : 'qt', savedCheckpointLeftForRestart: true,
    faultScope: 'Synthetic project bytes only; automatic failure uses the real startup entry point in the loaded page.' };
  fs.writeFileSync(path.join(runOutput, 'recovery-startup-results.json'), JSON.stringify(result, null, 2));
  return result;
}
