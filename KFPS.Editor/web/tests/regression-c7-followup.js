async page => page.evaluate(async () => {
  const shapes = Array.from({ length: 2400 }, (_, i) => ({ type: 1048677,
    color: [60, 100, 140, 255], data: [(i % 60) * 9, Math.floor(i / 60) * 9, .05, .05, 0, 0, 0] }));
  await loadProjectPayload({ shapes, name: "C7 boundary probe" });
  const object = vinylObjects()[0]; object.kloudy.pixel_art_generated = true;
  const encoded = typeof captureAssetSelection === "function"
    ? (canvas.setActiveObject(object), captureAssetSelection()) : [objectToShape(object)];
  const response = await fetch("/api/fabric-editor/assets", { method: "POST", headers: {
    ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" }, body: JSON.stringify({
      action: "save", payload: { format: "kfps_editor_asset_v1", name: "Generated", shapes: encoded } }) });
  const asset = { status: response.status, body: await response.json() };
  await saveProject();
  const original = renderHistoryList;
  renderHistoryList = () => { throw Error("Injected C7 New presenter failure"); };
  let error = null;
  try { await startBlankCanvas(); } catch (err) { error = err.message; }
  finally { renderHistoryList = original; }
  const blank = { error, layers: vinylObjects().length, history: editorHistory.entries.length,
    recovery: editorRecovery.status };
  document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
  await clearAutosave(); documentDirty = false;
  return { passed: asset.status === 200 && blank.history === 1 && !error, asset, blank };
})
