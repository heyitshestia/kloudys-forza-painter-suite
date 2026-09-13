async page => {
  const check = (v, message) => { if (!v) throw new Error(message); };
  const idle = () => page.waitForFunction(() => !editorAssetLibrary.busy);
  const fixture = await page.evaluate(async () => {
    const shapes = [
      { type: 1048787, type_word: 211, resource_family: "Gradient_Shapes", resource_index: 11, color: [230, 80, 170, 200], data: [0, 0, 2, 2, 0, 0, 0], editor_group_id: "source", editor_group_name: "Mixed group", editor_locked: true },
      { type: 1048678, color: [255, 255, 255, 255], data: [0, 0, .25, .25, 0, 0, 1], mask: true, editor_group_id: "source", editor_group_name: "Mixed group" },
      { type: 1048677, color: [20, 220, 60, 255], data: [500, 0, 1, 1, 0, 0, 0], editor_hidden: true },
    ];
    const result = await (await fetch("/api/fabric-editor/assets", { method: "POST", headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" }, body: JSON.stringify({ action: "save", payload: { format: "kfps_editor_asset_v1", name: "Mixed asset", shapes } }) })).json();
    if (!result.ok) throw new Error(JSON.stringify(result));
    KfpsEditorPreferences.setItem("kloudyFabricFavorites", "[1048677,1048678]");
    KfpsEditorPreferences.setItem("kloudyFabricOverlapCycle", "1");
    await KfpsEditorPreferences.flush();
    return result.entry;
  });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await page.evaluate(() => { document.querySelectorAll("dialog[open]").forEach(d => d.close()); activateDockPanel("assetsPane"); });
  await idle();
  check(await page.evaluate(() => KfpsEditorPreferences.getItem("kloudyFabricFavorites") === "[1048677,1048678]" && document.getElementById("overlapCycle").checked), "Favorites and overlap preference must survive reload");
  const card = page.locator(`[data-asset-id="${fixture.id}"]`);
  await page.locator("#assetSearch").fill("Mixed asset");
  await page.waitForFunction(id => { const img = document.querySelector(`[data-asset-id="${id}"] img`); return img?.complete && img.naturalWidth > 0; }, fixture.id);
  await page.evaluate(async () => { documentDirty = false; await startBlankCanvas(); });
  await card.locator(".assetActions > button").click(); await idle();
  const inserted = await page.evaluate(() => snapshotShapes());
  check(inserted.length === 3 && inserted[0].type === 1048787 && inserted[1].mask && inserted[2].editor_hidden, "Mixed asset must preserve gradients, masks and hidden layers");
  check(inserted.every(s => !s.editor_locked) && inserted[0].editor_group_id !== "source" && inserted[0].editor_group_id === inserted[1].editor_group_id, "Copies must use independent groups and paste-compatible unlocking");
  await page.evaluate(() => {
    window.__assetBlob = null;
    const create = URL.createObjectURL, click = HTMLAnchorElement.prototype.click;
    URL.createObjectURL = function(blob) { window.__assetBlob = blob; return create.call(this, blob); };
    HTMLAnchorElement.prototype.click = function() {};
    window.__restoreAssetDownload = () => { URL.createObjectURL = create; HTMLAnchorElement.prototype.click = click; };
  });
  try {
    await card.locator("summary").click(); await card.getByRole("button", { name: "Export Asset", exact: true }).click(); await idle();
    const exported = await page.evaluate(async () => JSON.parse(await window.__assetBlob.text()));
    check(exported.format === "kfps_editor_asset_v1" && !exported.id && !exported.source_path && exported.shapes[0].editor_group_id === "source", "Portable asset must be independent of library paths and inserted copies");
    await page.locator("#assetInput").setInputFiles({ name: "shared.kfps-asset.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(exported)) });
    await idle();
    check(await page.locator(".editorAsset").count() === 2, "Reimport must create a separate asset, not replace the original");
  } finally { await page.evaluate(() => window.__restoreAssetDownload()); }
  await card.locator("summary").click(); await card.getByRole("button", { name: "Delete", exact: true }).click();
  await page.locator("#textPromptDialog").waitFor({ state: "hidden" });
  await page.locator("#confirmationDialogConfirm").click();
  await idle();
  check(await card.count() === 0, "Delete must remove only the selected saved asset");
  check(await page.evaluate(shapes => JSON.stringify(snapshotShapes()) === JSON.stringify(shapes), inserted), "Deleting the saved asset must not change inserted artwork");
  const capacity = await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 2999 }, (_, i) => ({ type: 1048677, data: [i % 60 * 5, Math.floor(i / 60) * 5, .05, .05, 0, 0, 0], color: [20, 150, 200, 255] })) });
    const previous = editorHistory.entries.length;
    await insertCopiedShapesNow([{ type: 1048677, data: [0,0,1,1,0,0,0], color: [255,255,255,255] }, { type: 1048677, data: [0,0,1,1,0,0,0], color: [255,255,255,255] }], { asset: true });
    return vinylObjects().length === 2999 && editorHistory.entries.length === previous;
  });
  check(capacity, "Near-capacity insertion must be rejected atomically");
  await page.locator("#assetInput").setInputFiles({ name: "bad.kfps-asset.json", mimeType: "application/json", buffer: Buffer.from("{broken") }); await idle();
  check(await page.locator("#assetStatus").getAttribute("class") === "assetError", "Malformed asset must display a recoverable error");
  return { reload: true, mixedAsset: true, exportImport: true, independentDeletion: true, layerLimit: true, invalidImport: true };
}
