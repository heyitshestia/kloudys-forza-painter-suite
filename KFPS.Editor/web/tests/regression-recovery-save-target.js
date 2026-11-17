async page => {
  const assert = require('node:assert/strict');
  page.setDefaultTimeout(20000);
  const info = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
  const root = fs.realpathSync(path.resolve(__dirname, '../../../runtime/test-runs'));
  const relative = path.relative(root, fs.realpathSync(info.profile));
  assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Isolated profile required');
  const titleA = 'Recovery target A ' + Date.now();
  const titleB = titleA.replace(' A ', ' B ');
  const command = async id => {
    if (!await page.locator('#' + id).isVisible()) await page.locator('#workspaceFileMenu').click();
    await page.locator('#' + id).click();
  };
  const saveAs = async title => {
    await command('saveProjectAs');
    await page.locator('#textPromptInput').fill(title);
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(title => currentProjectName === title && !projectSaveInProgress && !isDocumentDirty(), title);
    return page.evaluate(() => ({ name: currentProjectName, receipt: editorProjects.association, shapes: snapshotShapes() }));
  };
  const edit = async () => {
    await page.locator('.upper-canvas').click({ position: { x: 8, y: 8 } });
    await page.evaluate(() => selectObjects(vinylObjects().slice(0, 3), 'save target test'));
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(() => !nudgeHistoryPending && isDocumentDirty());
  };
  const disk = receipt => page.evaluate(async receipt => {
    const response = await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(receipt.target_id)}`, { headers: EDITOR_MUTATION_HEADERS });
    if (!response.ok) throw Error('Project read failed: ' + response.status);
    return response.json();
  }, receipt);
  await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: Array.from({ length: 300 }, (_, i) => ({
      type: 1048677, color: [50 + i % 170, 100, 200, 255],
      data: [(i % 30) * 15, Math.floor(i / 30) * 15, 0.08, 0.08, 0, 0, 0],
    })) });
  });
  const a = await saveAs(titleA), originalDisk = await disk(a.receipt);
  await page.evaluate(async () => {
    await flushPendingAutosave();
    window.__saveTargetPayload = await readAutosavePayload();
    window.__saveTargetVerify = editorProjects.verify;
    window.__saveTargetGateEntered = false;
    const gate = new Promise(resolve => { window.__saveTargetRelease = resolve; });
    editorProjects.verify = async function (receipt) {
      const result = await __saveTargetVerify.call(this, receipt);
      __saveTargetGateEntered = true;
      await gate;
      return result;
    };
    window.__saveTargetRecovery = recoverAutosavePayload(__saveTargetPayload);
  });
  try {
    await page.waitForFunction(() => __saveTargetGateEntered);
    await edit();
    const b = await saveAs(titleB);
    assert.notEqual(b.receipt.target_id, a.receipt.target_id);
    assert.equal(await page.evaluate(async () => { __saveTargetRelease(); return __saveTargetRecovery; }), true);
    assert.deepEqual(await page.evaluate(() => editorProjects.association), b.receipt,
      'Late verification replaced the Save As receipt');
    assert.equal(await page.evaluate(() => currentProjectName), titleB);
    await edit();
    const expected = await page.evaluate(() => JSON.stringify(snapshotShapes()));
    await command('saveProject');
    await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty());
    const finalReceipt = await page.evaluate(() => editorProjects.association);
    assert.equal(finalReceipt.target_id, b.receipt.target_id, 'Ordinary Save returned to project A');
    assert.deepEqual(await disk(a.receipt), originalDisk, 'Original project A was changed');
    assert.equal(JSON.stringify((await disk(finalReceipt)).payload.shapes), expected,
      'Project B did not receive the exact serialized new edit');
    await page.evaluate(async () => {
      await flushPendingAutosave();
      const payload = await readAutosavePayload();
      if (!payload.editor_session.saved || payload.editor_session.receipt.target_id !== editorProjects.association.target_id)
        throw Error('Checkpoint retained a stale save target');
    });
    return { passed: true, layers: 300, delayedVerification: true, saveAsViaUI: true,
      originalUnchanged: true, nextSaveExactDestination: true, checkpointTargetVerified: true };
  } finally {
    await page.evaluate(async () => {
      __saveTargetRelease();
      await __saveTargetRecovery;
      editorProjects.verify = __saveTargetVerify;
      for (const key of Object.keys(window).filter(key => key.startsWith('__saveTarget'))) delete window[key];
    });
  }
}
