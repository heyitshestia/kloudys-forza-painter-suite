async page => {
  await page.evaluate(async () => {
    const shape = { type: 1048677, color: [50, 155, 170, 255], data: [0, 0, 1, 1, 0, 0, 0] };
    for (let i = 0; i < 45; i++) {
      const response = await fetch("/api/fabric-editor/assets", { method: "POST", headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" }, body: JSON.stringify({ action: "save", payload: { format: "kfps_editor_asset_v1", name: `Layout ${String(i).padStart(2, "0")} ${"LongAssetName".repeat(4)}`, shapes: [shape] } }) });
      if (!response.ok) throw new Error("Could not prepare the layout fixture");
    }
    await loadPayload({ shapes: [shape] });
    canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel();
    activateDockPanel("assetsPane");
  });
  await page.waitForFunction(() => !editorAssetLibrary.busy);
  await page.locator("#assetSearch").fill("Layout");
  if (await page.locator(".editorAsset").count() !== 40) throw new Error("Initial tile count must be bounded to 40");
  await page.locator("#assetMore").click();
  if (await page.locator(".editorAsset").count() !== 45) throw new Error("Show More must expose the remaining assets");
  const results = [];
  for (const theme of ["blackout", "whiteout"]) {
    await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
    for (const size of [{ width: 1280, height: 720 }, { width: 1600, height: 900 }]) {
      await page.setViewportSize(size);
      await page.locator("#assetSearch").fill("Layout 00");
      await page.locator(".editorAsset").first().scrollIntoViewIfNeeded();
      await page.waitForFunction(() => { const img = document.querySelector(".editorAsset img"); return img?.complete && img.naturalWidth; });
      const result = await page.evaluate(() => {
        const card = document.querySelector(".editorAsset"), bounds = card.getBoundingClientRect(), name = card.querySelector("strong"), preview = card.querySelector(".assetPreview").getBoundingClientRect();
        return { fitsWindow: document.documentElement.scrollWidth <= innerWidth, cardContentFits: card.scrollWidth <= card.clientWidth + 1 && name.scrollWidth <= name.clientWidth + 1, square: Math.abs(preview.width - preview.height) < 2 };
      });
      if (Object.values(result).some(value => !value)) throw new Error(`Asset layout failed: ${JSON.stringify(result)}`);
      await page.screenshot({ path: `assets-${theme}-${size.width}.png` });
      results.push({ theme, ...size, ...result });
    }
  }
  return results;
}
