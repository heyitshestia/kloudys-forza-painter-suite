async page => {
  const before = await page.evaluate(async () => {
    const listing = await (await fetch("/api/fabric-editor/assets")).json();
    const entry = listing.entries.find(item => item.name === "Mixed asset");
    if (listing.entries.length !== 46 || !entry) throw new Error("Asset library did not survive process restart");
    if (editorSettings.getItem("kloudyFabricFavorites") !== "[1048677,1048678]" || !document.getElementById("overlapCycle").checked) throw new Error("Favorites or overlap preference did not survive process restart");
    activateDockPanel("assetsPane");
    return { entry, resumed: snapshotShapes() };
  });
  await page.waitForFunction(() => !editorAssetLibrary.busy);
  await page.locator("#assetSearch").fill("Mixed asset");
  await page.locator(`[data-asset-id="${before.entry.id}"] .assetActions > button`).click();
  await page.waitForFunction(() => !editorAssetLibrary.busy);
  const result = await page.evaluate(() => snapshotShapes());
  if (JSON.stringify(result.slice(0, before.resumed.length)) !== JSON.stringify(before.resumed)) throw new Error("Asset insertion altered the automatically resumed canvas");
  const inserted = result.slice(before.resumed.length);
  if (inserted.length !== 3 || inserted[0].type !== 1048787 || !inserted[1].mask || !inserted[2].editor_hidden) throw new Error("Persisted mixed asset failed after restarting the native window");
  return { fullNativeProcessRestart: true, assets: 46, legacyPreferencePreserved: true, overlapPreferencePreserved: true, mixedAssetReopened: true, resumedLayersPreserved: before.resumed.length };
}
