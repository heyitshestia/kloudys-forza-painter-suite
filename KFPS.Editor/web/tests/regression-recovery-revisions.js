async page => {
  const checks = [];
  await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: [{ type: 1048677, color: [100, 160, 220, 255], data: [0, 0, 1, 1, 0, 0, 0] }] });
    window.revisionEdit = () => { const o = vinylObjects()[0]; o.left += 37; o.setCoords(); pushHistory("revision regression"); };
    window.revisionX = () => objectToShape(vinylObjects()[0], { includeEditorMeta: true }).data[0];
    window.originalPersistenceRequest = editorPersistence.request.bind(editorPersistence);
    window.holdSaveAcknowledgement = () => {
      window.saveReached = false;
      const gate = new Promise(resolve => { window.releaseSave = resolve; });
      editorPersistence.request = async (operation, data) => {
        const result = await originalPersistenceRequest(operation, data);
        if (operation === "saveProject") { saveReached = true; await gate; }
        return result;
      };
    };
    currentProjectName = "Revision during save";
    revisionEdit();
    window.capturedX = revisionX();
    holdSaveAcknowledgement();
    window.savingRevision = saveProject();
  });
  try {
    await page.waitForFunction(() => saveReached);
    const first = await page.evaluate(async () => {
      revisionEdit(); selectObjects([vinylObjects()[0]], "save-race nudge"); nudgeSelected(1, 0);
      const newerX = revisionX();
      releaseSave(); await savingRevision;
      editorPersistence.request = originalPersistenceRequest;
      await flushPendingAutosave();
      if (!documentDirty) throw new Error("Save marked newer edit clean");
      const recovery = await readAutosavePayload();
      if (recovery.shapes[0].data[0] !== newerX) throw new Error("Save discarded newer recovery");
      await refreshProjectBrowser();
      const entry = projectBrowserState.entries.find(item => item.title === currentProjectName);
      if (!entry) throw new Error("Actual saved project missing");
      const saved = await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json();
      if (saved.payload.shapes[0].data[0] !== capturedX) throw new Error("Saved artifact does not match captured revision");
      await loadProjectPayload(saved.payload, entry.title);
      if (revisionX() !== capturedX || documentDirty) throw new Error("Saved artifact reopen failed");
      await recoverAutosavePayload(recovery);
      if (revisionX() !== newerX) throw new Error("Recovery reopen lost newer edit");
      return { capturedX, newerX, savedReopened: true, recoveryReopened: true };
    });
    checks.push(first);
    await page.evaluate(() => {
      currentProjectName = "New document save race";
      holdSaveAcknowledgement();
      window.savingRevision = saveProject();
    });
    await page.waitForFunction(() => saveReached);
    await page.evaluate(async () => {
      await loadPayload({ shapes: [{ type: 1048677, color: [10, 20, 30, 255], data: [500, 0, 1, 1, 0, 0, 0] }] });
      currentProjectName = "New unsaved document";
      revisionEdit();
      releaseSave(); await savingRevision;
      editorPersistence.request = originalPersistenceRequest;
      if (currentProjectName !== "New unsaved document" || !documentDirty) throw new Error("Older save clobbered new workspace");
    });
    checks.push("new document during real save delivery is preserved");
    await page.evaluate(async () => {
      await clearAutosave();
      const newer = Math.max(Date.now(), Math.ceil(editorRecovery.revision / 1000)) + 2000;
      const shape = x => ({ type: 1048677, color: [10, 20, 30, 255], data: [x, 0, 1, 1, 0, 0, 0] });
      // A pre-versioned browser checkpoint newer than the clear marker can migrate.
      localStorage.setItem(AUTOSAVE_KEY, JSON.stringify({ name: "Legacy recovery", saved_at: new Date(newer).toISOString(), shapes: [shape(888)] }));
      const selected = await readAutosavePayload();
      if (selected?.shapes[0].data[0] !== 888) throw new Error("Legacy timestamp migration failed");
      if (!await recoverAutosavePayload(selected) || revisionX() !== 888) throw new Error("Legacy recovery did not reopen");
      await flushPendingAutosave();
      if (!editorRecovery.status.serverOk) throw new Error("Legacy recovery was not migrated to the app folder");
    });
    checks.push("legacy timestamp and exact recovery migration");
    return { passed: true, checks };
  } finally {
    await page.evaluate(async () => {
      releaseSave?.(); editorPersistence.request = originalPersistenceRequest;
      await clearAutosave(); documentDirty = false;
    });
  }
}
