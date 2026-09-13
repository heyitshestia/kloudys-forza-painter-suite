async page => {
  const checks = [];
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 300 }, (_, index) => ({
      type: 1048677, color: [40, 150, 210, 255], data: [index * 2, 0, .5, .5, 0, 0, 0],
    })) });
    currentProjectName = "Receipt fixture";
    const original = renderHistoryList;
    renderHistoryList = () => { throw Error("Injected history display failure"); };
    try { await saveProject(); } finally { renderHistoryList = original; }
    if (documentDirty || savedHistoryState !== currentHistoryState() || !editorProjects.association) throw Error("Committed save lost its clean state");
    if (document.querySelector("dialog[open]")) throw Error(`Committed save has an open dialog: ${document.querySelector("dialog[open]").id}: ${document.querySelector("dialog[open]").textContent}`);
    await flushPendingAutosave();
    const recovery = await readAutosavePayload();
    if (!recovery.editor_session.saved || !recovery.editor_session.receipt) throw Error("Recovery did not retain the save receipt");
    window.receiptRecovery = recovery;
    const receipt = editorProjects.association;
    const disk = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(receipt.target_id)}`);
    if (disk.payload.shapes.length !== 300 || disk.receipt.fingerprint !== receipt.fingerprint) throw Error("Saved artifact did not reopen exactly");
    const response = await fetch("/api/fabric-editor/save-project", {
      method: "POST", headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" },
      body: JSON.stringify({ name: currentProjectName, payload: { shapes: [] }, overwrite: true }),
    });
    if (!response.ok) throw Error("External-change fixture failed");
    vinylObjects()[0].left += 20; pushHistory("edit after external replacement");
    await saveProject();
    if (!documentDirty || !document.querySelector("dialog[open]")) throw Error("Conflict did not preserve edits and show a warning");
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    const changed = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(receipt.target_id)}`);
    if (changed.payload.shapes.length !== 0) throw Error("Conflict overwrote the external version");
    await recoverAutosavePayload(receiptRecovery);
    if (!documentDirty || editorProjects.association) throw Error("Recovery falsely claimed association with changed file");
  });
  checks.push("300-shape committed display failure, exact reopen, conflict and stale recovery association");
  await page.evaluate(() => {
    window.receiptRequest = editorPersistence.request.bind(editorPersistence);
    window.receiptWrites = 0;
    editorPersistence.request = async (operation, data) => {
      const response = await receiptRequest(operation, data);
      if (operation === "saveProject") {
        receiptWrites++;
        throw Object.assign(Error("Injected lost worker reply after server commit"), { code: "worker_timeout" });
      }
      return response;
    };
  });
  try {
    await page.evaluate(async () => {
      currentProjectName = "Lost receipt fixture";
      await saveProject();
      if (documentDirty || !editorProjects.association) throw Error("Lost reply was not reconciled");
      if (!await editorProjects.verify(editorProjects.association)) throw Error("Reconciled file is not on disk");
    });
    if (await page.evaluate(() => receiptWrites) !== 1) throw Error("Save was replayed");
  } finally { await page.evaluate(() => { editorPersistence.request = receiptRequest; }); }
  checks.push("lost write reply reconciled with exactly one POST");
  await page.evaluate(async () => {
    await loadPayload({ shapes: [{ type: 1048677, color: [30, 50, 70, 255], data: [0, 0, 1, 1, 0, 0, 0] }] }, { projectName: null });
    window.pendingReceiptSave = saveProjectAs();
    window.reentrantReceiptSave = saveProjectAs();
  });
  await page.locator("#textPromptInput").fill("Stale naming fixture");
  await page.evaluate(async () => {
    await loadPayload({ shapes: [{ type: 1048677, color: [80, 100, 120, 255], data: [200, 0, 1, 1, 0, 0, 0] }] }, { projectName: null });
  });
  await page.locator("#textPromptInput").press("Enter");
  await page.evaluate(async () => {
    await pendingReceiptSave; await reentrantReceiptSave;
    const listing = await readEditorDocument(PROJECT_BROWSER_API);
    if (listing.entries.some(entry => entry.title === "Stale naming fixture")) throw Error("Stale dialog saved a different document");
    if (vinylObjects().length !== 1 || currentProjectName || projectSaveInProgress) throw Error("Naming crossed a document boundary");
    await clearAutosave(); documentDirty = false;
  });
  checks.push("naming is single-flight and fenced across document changes");
  return { passed: true, checks };
}
