async (page, options = {}) => {
  page.setDefaultTimeout(20000);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const idle = () => page.waitForFunction(() => !editorCommands.busy && !projectSaveInProgress);
  const blur = () => page.evaluate(() => document.activeElement?.blur());
  const snapshot = () => page.evaluate(() => JSON.stringify(snapshotShapes()));
  const saveAs = async name => {
    await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill(name);
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  };
  if (options.workflowRecoverFrom) {
    const source = path.resolve(options.workflowRecoverFrom);
    check(source.startsWith(path.resolve(output, '..') + path.sep), 'Recovery fixture must be in this test-run root');
    const expected = fs.readFileSync(path.join(source, 'recovery-expected.json'), 'utf8');
    await page.locator('#loadProject').click();
    await page.locator('#recentAutosavesTab').click();
    await page.waitForFunction(() => !projectBrowserState.loading && !projectBrowserState.restoring);
    await page.locator('.projectBrowserEntry').first().dblclick();
    if (await page.locator('#confirmationDialog').isVisible()) await page.locator('#confirmationDialogConfirm').click();
    await page.locator('#projectBrowserDialog').waitFor({ state: 'hidden' });
    check(await snapshot() === expected, 'Abrupt-exit recovery changed the grouped/coloured artwork');
    await saveAs('Recovered workflow checkpoint');
    return { abruptExitRecoveredExactly: true, manualAutosavePicker: true, saveAfterRecovery: true };
  }
  await page.evaluate(async () => {
    await clearAutosave(); resetShortcuts();
    await loadPayload({ shapes: Array.from({ length: 9 }, (_, i) => ({
      type: 1048677, data: [i * 110 - 400, i * 5, .3, .25, i * 7, 0, 0],
      color: [30 + i * 10, 100, 180, 200], editor_id: `durable-${i}`,
      ...(i < 3 ? { editor_group_id: 'old-a', editor_group_name: 'Legacy A' }
        : i < 6 ? { editor_group_id: 'old-b', editor_group_name: 'Legacy B' } : {})
    })) });
    favoriteColors[0] = [201, 67, 103, 255]; saveFavoriteColors();
    $('layerSearch').value = ''; refreshLayers();
  });
  // Legacy flat-group projects and partial selections from multiple groups.
  await page.evaluate(() => selectObjects([vinylObjects()[0], vinylObjects()[3]], 'test'));
  await blur(); await page.keyboard.press('Control+c');
  check(await page.evaluate(() => editorClipboard.shapes.every(shape => !shape.editor_group_id && !shape.editor_group_path)),
    'Partial selections retained old group wrappers');
  await page.evaluate(() => selectObjects(vinylObjects().slice(0, 4), 'test'));
  await blur(); await page.keyboard.press('Control+c');
  check(await page.evaluate(() => editorClipboard.shapes.filter(shape => shape.editor_group_id).length === 3),
    'Mixed full/partial selection lost the complete group or retained the partial group');
  const before = await snapshot();
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press('Control+v'); await idle();
    check(await page.evaluate(i => {
      const all = vinylObjects(), selected = selectedVinylObjects();
      const groupIds = all.flatMap(object => KfpsEditorLayerGroups.objectPath(object).map(group => group.id));
      return all.length === 9 + (i + 1) * 4 && selected.length === 4
        && new Set(all.map(object => object.kloudy.editor_id)).size === all.length
        && new Set(groupIds).size === i + 3
        && selected.filter(object => object.kloudy.group_id).length === 3;
    }, i), `Repeated paste identity/group collision at ${i}`);
  }
  const pasted = await snapshot();
  for (let i = 0; i < 15; i++) { await page.locator('#undoBtn').click(); await idle(); }
  check(await snapshot() === before, 'Fifteen paste undos drifted');
  for (let i = 0; i < 15; i++) { await page.locator('#redoBtn').click(); await idle(); }
  check(await snapshot() === pasted, 'Fifteen paste redos drifted or allocated new identities');
  // Clipboard persistence failure must not disable the in-memory copy.
  await page.evaluate(() => {
    window.__storageSet = Storage.prototype.setItem;
    Storage.prototype.setItem = function(key, value) {
      if (key === EDITOR_CLIPBOARD_KEY) throw new DOMException('Injected clipboard quota', 'QuotaExceededError');
      return __storageSet.call(this, key, value);
    };
    selectObjects([vinylObjects()[0]], 'test'); lastLayerListKey = null;
  });
  try { await blur(); await page.keyboard.press('Control+c'); }
  finally { await page.evaluate(() => { Storage.prototype.setItem = __storageSet; delete window.__storageSet; }); }
  await page.keyboard.press('Control+v'); await idle();
  check(await page.evaluate(() => selectedVinylObjects().length === 1 && !selectedVinylObjects()[0].kloudy.group_id),
    'Clipboard quota failure lost the independent copied shape');
  await saveAs('Durable group workflow');
  const diskBefore = await page.evaluate(async () => {
    await refreshProjectBrowser();
    const entry = projectBrowserState.entries.find(entry => entry.title === currentProjectName);
    window.__durableProjectId = entry.id;
    return (await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json()).payload;
  });
  // Hold only the acknowledgment of a real committed save, then use new controls.
  await page.evaluate(() => {
    window.__request = editorPersistence.request.bind(editorPersistence);
    window.__saveReached = false;
    const gate = new Promise(resolve => { window.__releaseSave = resolve; });
    editorPersistence.request = async (operation, data) => {
      const result = await __request(operation, data);
      if (operation === 'saveProject') { __saveReached = true; await gate; }
      return result;
    };
    window.__saving = saveProject();
  });
  try {
    await page.waitForFunction(() => __saveReached);
    await page.evaluate(() => selectObjects([vinylObjects().find(object => object.kloudy.editor_id === 'durable-8')], 'test'));
    await page.locator('#groupActions').click(); await page.locator('#addSelectedToGroup').click();
    await page.locator('#addToGroupTarget').selectOption('old-a');
    await page.locator('#addToGroupDialog button[value=add]').click();
    await blur(); await page.keyboard.press('1');
  } finally {
    await page.evaluate(async () => { __releaseSave(); await __saving; editorPersistence.request = __request; });
  }
  const newer = await snapshot();
  check(await page.evaluate(() => documentDirty), 'Save acknowledgment erased newer grouping/colour edit');
  check(await page.evaluate(async before => {
    await flushPendingAutosave();
    const saved = (await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(__durableProjectId)}`)).json()).payload;
    const recovered = await readAutosavePayload();
    return JSON.stringify(saved.shapes) === JSON.stringify(before.shapes)
      && JSON.stringify(recovered.shapes) === JSON.stringify(snapshotShapes());
  }, diskBefore), 'Committed save or newer recovery contains the wrong revision');
  // Reject the next write before commit. Existing saved project and edits survive.
  await page.evaluate(() => {
    editorPersistence.request = (operation, data) => operation === 'saveProject'
      ? Promise.reject(new Error('Injected write failure')) : __request(operation, data);
  });
  try {
    await page.locator('#saveProject').click();
    await page.locator('#messageDialog').waitFor({ state: 'visible' }); await idle();
    check(await snapshot() === newer && await page.evaluate(() => documentDirty), 'Failed write changed or marked unsaved work clean');
    check(await page.evaluate(async before => {
      const saved = (await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(__durableProjectId)}`)).json()).payload;
      return JSON.stringify(saved.shapes) === JSON.stringify(before.shapes) && !$('saveProject').disabled;
    }, diskBefore), 'Failed write damaged the saved project or left Save disabled');
  } finally {
    await page.evaluate(() => { editorPersistence.request = __request; $('messageDialog').close(); });
  }
  await page.locator('#saveProject').click();
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => {
    const saved = (await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(__durableProjectId)}`)).json()).payload;
    await loadProjectPayload(saved, 'Durable group workflow');
  });
  check(await snapshot() === newer, 'Save retry/reopen lost grouped or coloured shapes');
  if (options.workflowAbrupt) {
    await page.evaluate(() => selectObjects([vinylObjects()[0]], 'test'));
    await blur(); await page.keyboard.press('1');
    await page.evaluate(async () => {
      await flushPendingAutosave(); await KfpsEditorPreferences.flush();
      if (!documentDirty || !editorRecovery.status.serverOk || !editorRecovery.status.browserOk) throw Error('Crash fixture is not durable and unsaved');
    });
    fs.writeFileSync(path.join(output, 'recovery-expected.json'), await snapshot());
  }
  return { legacyGroups: true, mixedPartialAndFullCopy: true, repeatedPastes: 15,
    exactUndoRedo: true, clipboardQuotaFallback: true, editsDuringRealSave: true,
    failedWritePreservesBothRevisions: true, retryAndReopen: true, abruptExitPrepared: !!options.workflowAbrupt };
}
