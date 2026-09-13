async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  const initial = await h.setupDerived(page, output, { ...options, layers: 2400 });
  const original = await h.snapshot(page), checks = [];
  const target = await page.evaluate(() => {
    const objects = vinylObjects().filter(object => resolvedResourceForObject(object)?.family === "Primitives" && resolvedResourceForObject(object)?.index === 27);
    return { id: objects[0].kloudy.editor_id, word: shapeWordForObject(objects[0]), count: objects.length };
  });
  h.check(target.count > 200, "Global replacement must exercise many actual handmade shapes");
  const ready = () => page.waitForFunction(() => !historyLocked && !recoveryRestoreDepth);
  const pickReplacement = async () => {
    await page.locator("#shapeSearch").fill("");
    await page.locator("#shapeFamily").selectOption("Primitives");
    await page.waitForFunction(() => document.getElementById("shapeGrid").getAttribute("aria-busy") === "false");
    await page.locator('#shapeGrid [data-resource-key="Primitives:1"]').click();
  };
  await page.locator("#changeSelectedShape").click();
  await page.locator("#globalShapeReplacePanel").waitFor({ state: "visible" });
  h.check(await page.locator(".usedShapeButton").count() >= 47, "Global replacement omitted used resource types");
  await page.locator("#cancelGlobalShapeReplace").click();
  h.check(await h.snapshot(page) === original, "Cancelling global replacement changed artwork");
  checks.push({ name: "used-types-and-cancel" });
  await h.selectId(page, target.id);
  h.check(await page.locator(".layerRow.active .layerLock").count() === 1, "Selected target lock is not unique");
  await page.locator(".layerRow.active .layerLock").click();
  await page.locator("#clearLayerSelection").click();
  const locked = await h.snapshot(page);
  await page.locator("#changeSelectedShape").click();
  await page.locator(".usedShapeButton").filter({ hasText: new RegExp(` / word ${target.word}\\s*$`) }).click();
  await pickReplacement();
  await page.waitForFunction(() => !pendingGlobalShapeReplacement && !historyLocked);
  const replaced = JSON.parse(await h.snapshot(page)), before = JSON.parse(locked);
  const newType = await page.evaluate(() => editorCatalog.resourceToTypeCode("Primitives", 1));
  let changed = 0;
  for (let index = 0; index < before.length; index++) {
    const a = before[index], b = replaced[index];
    h.check(a.editor_id === b.editor_id, "Global replacement changed layer order or identity");
    if (a.type_word === target.word && a.editor_id !== target.id) {
      h.check(b.type === newType, "Global replacement skipped an unlocked matching shape");
      h.check(JSON.stringify(a.color) === JSON.stringify(b.color) && a.data.every((value, index) => Math.abs(value - b.data[index]) < 1e-8), "Global replacement changed color or transform");
      changed++;
    } else h.check(JSON.stringify(a) === JSON.stringify(b), "Global replacement changed a locked or unrelated layer");
  }
  h.check(changed === target.count - 1, "Unexpected number of global replacements");
  checks.push({ name: "global-replace-preserves-locks-order-color-transform", changed });
  await page.locator("#undoBtn").click(); await ready();
  h.check(await h.snapshot(page) === locked, "Global replacement undo was not exact");
  await page.locator("#redoBtn").click(); await ready();
  h.check(await h.snapshot(page) === JSON.stringify(replaced), "Global replacement redo was not exact");
  await page.locator("#undoBtn").click(); await ready();
  await page.locator("#undoBtn").click(); await ready();
  h.check(await h.snapshot(page) === original, "Lock/global replacement cleanup changed original artwork");
  await h.selectId(page, target.id);
  await page.locator("#changeSelectedShape").click();
  h.check(await page.locator("#shapePlacementMode").inputValue() === "replace", "Selected Change Shape did not arm replacement");
  await pickReplacement();
  await page.waitForFunction(type => selectedVinylObjects().length === 1 && selectedVinylObjects()[0].kloudy.type === type, newType);
  h.check(await page.locator("#shapePlacementMode").inputValue() === "top", "Selected replacement did not reset placement");
  await page.locator("#undoBtn").click(); await ready();
  h.check(await h.snapshot(page) === original, "Selected Change Shape undo changed artwork");
  checks.push({ name: "selected-change-button-reset-and-exact-undo" });
  await h.saveAs(page, "Replacement button qualification");
  await page.screenshot({ path: path.join(output, "replacement-buttons.png") });
  return { initial, checks, exactArtwork: true };
}
