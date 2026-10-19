const fs = require('node:fs');
const path = require('node:path');

module.exports = async function withSavedReloadRecovery(page, output, run) {
  const reload = page.reload.bind(page);
  const observations = [];
  page.reload = async (...args) => {
    const before = await page.evaluate(() => ({
      shapes: JSON.stringify(snapshotShapes()), reference: JSON.stringify(editorReference.sourceOverlayProjectState()),
      name: currentProjectName, dirty: isDocumentDirty(),
    }));
    if (before.dirty) throw Error('Chrome saved-reload adapter requires a saved document');
    const response = await reload(...args);
    await page.waitForFunction(() => window.KfpsDesktop?.ready);
    await page.waitForFunction(expected => document.querySelector('#autosaveRecoveryDialog')?.open
      || JSON.stringify(snapshotShapes()) === expected, before.shapes);
    const recovery = page.locator('#autosaveRecoveryDialog');
    const offered = await recovery.isVisible();
    if (offered) {
      await page.locator('#recoverAutosave').click();
      await page.waitForFunction(expected => !document.querySelector('#autosaveRecoveryDialog').open
        && !recoveryRestoreDepth && currentProjectName === expected.name
        && JSON.stringify(snapshotShapes()) === expected.shapes, before);
    }
    const after = await page.evaluate(() => ({
      shapes: JSON.stringify(snapshotShapes()), reference: JSON.stringify(editorReference.sourceOverlayProjectState()),
      name: currentProjectName, dirty: isDocumentDirty(),
    }));
    const entry = { offered, exactShapes: before.shapes === after.shapes,
      exactReference: before.reference === after.reference, sameName: before.name === after.name };
    observations.push(entry);
    fs.writeFileSync(path.join(output, 'chrome-reload-recovery.json'), JSON.stringify(observations, null, 2));
    if (!entry.exactShapes || !entry.exactReference || !entry.sameName) throw Error('Chrome recovery changed saved document');
    if (after.dirty) {
      await page.locator('#saveProject').click();
      await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty());
    }
    return response;
  };
  try { return await run(); }
  finally { page.reload = reload; }
};
