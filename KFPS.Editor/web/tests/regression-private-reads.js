async page => {
  const name = `private-reads-${Date.now()}`;
  await page.evaluate(async () => {
    await loadPayload({ shapes: [{ type: 1048677, data: [35, 50, .4, .6, 15, 0, 0], color: [255, 80, 180, 255] }] }, { strict: true });
    await flushPendingAutosave();
  });
  await page.locator("#saveProject").click();
  await page.locator("#textPromptInput").fill(name);
  await page.locator("#textPromptConfirm").click();
  await page.waitForFunction(() => !projectSaveInProgress && Boolean(currentProjectName) && !documentDirty);
  const initial = await page.evaluate(async () => {
    const unauthorised = await fetch(PROJECT_BROWSER_API);
    if (unauthorised.status !== 403) throw Error("Private project listing did not reject missing session");
    await refreshProjectBrowser();
    if (!projectBrowserState.entries.length) throw Error("Project browser is empty");
    const entry = projectBrowserState.entries.find(item => item.name.includes(currentProjectName));
    if (!entry) throw Error("Saved project is not listed");
    const document = await editorPersistence.request("fetchJSON", { url: `${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}` });
    if (document.payload.shapes.length !== 1) throw Error("Project worker read failed");
    const recovery = await readAutosavePayload();
    if (recovery.shapes.length !== 1) throw Error("Recovery read failed");
    const exported = await saveEditorJsonToAppFolder("private-preview", { shapes: snapshotShapes() });
    const response = await fetch("/api/fabric-editor/assets", { method: "POST",
      headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" },
      body: JSON.stringify({ action: "save", payload: { format: "kfps_editor_asset_v1", name: "Private preview", shapes: snapshotShapes() } }) });
    if (!response.ok) throw Error("Asset preparation failed");
    return { id: entry.id, shapes: snapshotShapes(), exported };
  });
  await page.locator('[data-panel="assetsPane"]').click();
  await page.locator("#assetRefresh").click();
  await page.waitForFunction(() => [...document.querySelectorAll("#assetGrid img")].some(image => image.complete && image.naturalWidth > 0 && image.src.startsWith("blob:")));
  await page.evaluate(() => {
    window.__privatePreviewUrls = new Set();
    window.__privatePreviewOriginals = [URL.createObjectURL, URL.revokeObjectURL];
    URL.createObjectURL = blob => { const url = __privatePreviewOriginals[0](blob); __privatePreviewUrls.add(url); return url; };
    URL.revokeObjectURL = url => { __privatePreviewUrls.delete(url); __privatePreviewOriginals[1](url); };
  });
  await page.route("**/api/fabric-editor/asset-preview?*", route => route.fulfill({ status: 200, contentType: "image/png", body: "invalid PNG" }));
  for (let i = 0; i < 3; i++) {
    await page.locator("#assetRefresh").click();
    await page.waitForFunction(() => !editorAssetLibrary.busy && document.querySelector("#assetGrid .assetPreview")?.textContent === "Preview unavailable");
    if (await page.evaluate(() => __privatePreviewUrls.size)) throw Error("Failed preview retained a blob URL");
  }
  await page.unroute("**/api/fabric-editor/asset-preview?*");
  await page.locator("#assetRefresh").click();
  await page.waitForFunction(() => [...document.querySelectorAll("#assetGrid img")].some(image => image.complete && image.naturalWidth > 0));
  await page.evaluate(() => { [URL.createObjectURL, URL.revokeObjectURL] = __privatePreviewOriginals; delete window.__privatePreviewOriginals; delete window.__privatePreviewUrls; });
  await page.evaluate(async () => {
    $("jsonBrowserSource").value = "editor";
    await openJsonBrowser();
  });
  await page.waitForFunction(() => $("jsonBrowserPreviewImage").naturalWidth > 0 && $("jsonBrowserPreviewImage").src.startsWith("blob:"));
  await page.screenshot({ path: path.join(output, "private-preview.png") });
  await page.locator("#closeJsonBrowser").click();
  await page.evaluate(() => flushPendingAutosave());
  await page.evaluate(id => { const value = new URL(location.href); value.searchParams.set("project", id); history.replaceState(null, "", value.href); }, initial.id);
  // The Chrome harness grants controlled reload the same allowance as its host;
  // an arbitrary navigation intentionally invokes the user close/save protocol.
  await page.reload();
  await page.waitForFunction(() => typeof currentProjectName !== "undefined" && Boolean(currentProjectName) && vinylObjects().length === 1);
  const reopened = await page.evaluate(async () => {
    await flushPendingAutosave();
    return { shapes: snapshotShapes(), preferencesError: KfpsEditorPreferences.error, token: Boolean(EDITOR_MUTATION_HEADERS["X-KFPS-Editor-Session"]) };
  });
  if (JSON.stringify(initial.shapes) !== JSON.stringify(reopened.shapes)) throw Error("Reopened artwork differs");
  if (reopened.preferencesError || !reopened.token) throw Error("Session/preferences did not survive reload");
  const result = { passed: true, saved: true, reopened: true, recovery: true, assetPreview: true, failedPreviewCleanup: true, jsonPreview: true, unauthorisedRejected: true };
  fs.writeFileSync(path.join(output, "private-reads.json"), JSON.stringify(result, null, 2));
  return result;
}
