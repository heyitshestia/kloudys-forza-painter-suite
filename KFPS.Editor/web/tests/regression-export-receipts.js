async page => {
  const results = await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 300 }, (_, i) => ({
      type: 1048677, color: [20, 70, 110, 255], data: [i, 0, .3, .3, 0, 0, 0], editor_group_id: "fixture", editor_group_name: "Fixture",
    })) }, { projectName: "Export receipt fixture" });
    const refresh = refreshJsonBrowser;
    const save = saveEditorJsonToAppFolder;
    window.exportDownload = downloadText;
    window.exportDownloads = [];
    downloadText = (name, text) => exportDownloads.push({ name, payload: JSON.parse(text) });
    window.savedExportReceipt = null;
    saveEditorJsonToAppFolder = async (...args) => savedExportReceipt = await save(...args);
    refreshJsonBrowser = () => { throw Error("Injected export list failure"); };
    try { await exportJson(); }
    finally { refreshJsonBrowser = refresh; saveEditorJsonToAppFolder = save; }
    if (!savedExportReceipt?.receipt || exportDownloads.length || document.querySelector("dialog[open]")) throw Error("Successful export caused a duplicate download or error dialog");
    const disk = await readEditorDocument(`${JSON_FILE_API}?id=${encodeURIComponent(savedExportReceipt.id)}`);
    if (disk.payload.shapes.length !== 300 || disk.payload.shapes.some(shape => Object.keys(shape).some(key => key.startsWith("editor_")))) throw Error("Export no longer round-trips as flat JSON");
    const request = editorPersistence.request.bind(editorPersistence);
    let writes = 0;
    editorPersistence.request = async (operation, data) => {
      const result = await request(operation, data);
      if (operation === "saveExport") { writes++; throw Object.assign(Error("Lost export reply"), { code: "worker_timeout" }); }
      return result;
    };
    try { await exportJson(); }
    finally { editorPersistence.request = request; }
    if (writes !== 1 || exportDownloads.length || document.querySelector("dialog[open]")) throw Error("Export reply was not reconciled without replay");
    return { flatRoundTrip: 300, refreshFailureNoDuplicate: true, lostReplySingleWrite: true };
  });
  await page.evaluate(() => {
    window.exportRequest = editorPersistence.request.bind(editorPersistence);
    editorPersistence.request = async (operation, data) => {
      if (operation === "saveExport") throw Error("Injected unconfirmed save");
      return exportRequest(operation, data);
    };
    window.pendingExport = exportJson();
  });
  try {
    await page.locator("#confirmationDialog").waitFor({ state: "visible" });
    if (await page.evaluate(() => exportDownloads.length)) throw Error("Uncertain export downloaded automatically");
    await page.locator("#confirmationDialogCancel").click();
    await page.evaluate(async () => { await pendingExport; window.pendingExport = exportJson(); });
    await page.locator("#confirmationDialogConfirm").click();
    await page.evaluate(async () => {
      await pendingExport;
      if (exportDownloads.length !== 1 || exportDownloads[0].payload.shapes.length !== 300) throw Error("Explicit download did not preserve the captured export");
      await clearAutosave(); documentDirty = false;
    });
  } finally {
    await page.evaluate(() => { editorPersistence.request = exportRequest; downloadText = exportDownload; });
  }
  return { ...results, uncertainDownloadRequiresConfirmation: true };
}
