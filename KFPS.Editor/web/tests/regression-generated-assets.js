async page => {
  const h = require(path.join(__dirname, "dense-human-fixture.cjs"));
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const initial = await h.setup(page, output, { layers: 2400 });
  const idle = () => page.waitForFunction(() => !editorAssetLibrary.busy && !pixelArtGenerationRunning && !editorCommands.busy);
  const prompt = async name => {
    await h.type(page, "#textPromptInput", name);
    await page.locator("#textPromptInput").press("Enter");
    await page.locator("#textPromptDialog").waitFor({ state: "hidden" });
  };
  const saveAsset = async name => {
    await page.locator('[data-panel="assetsPane"]').click();
    await page.locator("#assetSaveSelection").click(); await prompt(name); await idle();
    check(await page.locator(".editorAsset strong").filter({ hasText: name }).count() === 1, `Asset not saved: ${name}`);
  };
  const pixelFile = path.join(output, "pixel-source.svg");
  fs.writeFileSync(pixelFile, '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32"><rect width="48" height="32" fill="#20a0c0"/><rect x="8" y="8" width="16" height="16" fill="#f0c030"/></svg>');
  await page.locator('[data-tool-mode="pixelArt"]').click();
  await h.fileInput(page, "#pixelArtInput", pixelFile);
  await page.locator("#generatePixelArt").click(); await idle();
  const original = await h.snapshot(page);
  const generated = await page.evaluate(() => vinylObjects().filter(o => o.kloudy.pixel_art_generated).length);
  check(generated > 0 && generated < 100, "Generation did not create the intended small group");
  await saveAsset("Generated original");
  await h.type(page, "#layerSearch", "Human target");
  await page.locator(".layerRow").filter({ hasText: "Human target" }).click({ modifiers: ["Control"] });
  check(await page.evaluate(() => selectedVinylObjects().length) === generated + 1, "Mixed selection did not include manual and generated layers");
  await saveAsset("Mixed original");
  await h.select(page, "Human alternate"); await saveAsset("Legacy ordinary");
  const entries = await page.evaluate(async () => (await (await fetch("/api/fabric-editor/assets")).json()).entries);
  const id = entries.find(e => e.name === "Generated original").id;
  const card = page.locator(`[data-asset-id="${id}"]`);
  await card.locator("summary").click(); await card.getByRole("button", { name: "Rename", exact: true }).click();
  await prompt("Generated reusable"); await idle();
  await page.evaluate(() => {
    const create = URL.createObjectURL, click = HTMLAnchorElement.prototype.click;
    URL.createObjectURL = function(blob) { window.c8AssetBlob = blob; return create.call(this, blob); };
    HTMLAnchorElement.prototype.click = function() {};
    window.c8RestoreDownload = () => { URL.createObjectURL = create; HTMLAnchorElement.prototype.click = click; };
  });
  let portable;
  try {
    await card.locator("summary").click(); await card.getByRole("button", { name: "Export Asset", exact: true }).click(); await idle();
    portable = await page.evaluate(async () => JSON.parse(await c8AssetBlob.text()));
  } finally { await page.evaluate(() => c8RestoreDownload()); }
  check(!portable.id && portable.shapes.length === generated && portable.shapes.every(s => !Object.hasOwn(s, "editor_pixel_art_generated")), "Portable asset retains generator eligibility or wrong artwork");
  const imported = path.join(output, "portable.kfps-asset.json");
  fs.writeFileSync(imported, JSON.stringify({ ...portable, name: "Imported reusable" }));
  await h.fileInput(page, "#assetInput", imported); await idle();
  check(await page.locator(".editorAsset").count() === 4, "Portable asset did not import independently");
  check(await h.snapshot(page) === original, "Preparing/saving/renaming/exporting assets mutated live originals");
  const assets = await page.evaluate(async () => {
    const entries = (await (await fetch("/api/fabric-editor/assets")).json()).entries;
    return Promise.all(entries.map(async entry => ({ entry,
      payload: await (await fetch(`/api/fabric-editor/assets?id=${entry.id}`)).json() })));
  });
  await page.locator("#saveProjectAs").click(); await prompt("Generated assets checkpoint");
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => { await flushPendingAutosave(); await KfpsEditorPreferences.flush(); });
  fs.writeFileSync(path.join(output, "expected.json"), JSON.stringify({ original: JSON.parse(original), generated, assets }));
  await page.screenshot({ path: path.join(output, "generated-assets.png") });
  return { passed: true, initial, generated, assets: 4, originalsExact: true,
    realGenerateAndAssetButtons: true, downloadSinkCaptured: true, restartPending: true };
}
