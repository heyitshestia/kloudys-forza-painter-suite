async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  const expected = fs.readFileSync(options.expectedFile, "utf8"), count = JSON.parse(expected).length;
  await page.waitForFunction(count => vinylObjects().length === count && !recoveryRestoreDepth && !!editorReference.image, count, { timeout: 90000 });
  h.check(await h.snapshot(page) === expected, "New process recovery did not restore the exact endurance artwork");
  const expectedReference=JSON.parse(fs.readFileSync(path.join(path.dirname(options.expectedFile),'endurance-reference.json'),'utf8'));
  h.check(JSON.stringify(await h.referenceState(page))===JSON.stringify(expectedReference),"Restart changed the reference image state");
  h.check(await page.evaluate(() => currentProjectName) === "Handmade endurance checkpoint", "Restart lost project association");
  await page.locator("#selectAllLayers").click();
  h.check(await page.evaluate(() => selectedVinylObjects().length) === count, "Restart selection controls did not work");
  await page.locator("#clearLayerSelection").click();
  h.check(await h.snapshot(page) === expected, "Restart selection changed artwork");
  await page.locator("#fitView").click();
  await page.screenshot({ path: path.join(output, "endurance-restored.png") });
  return { exactNewProcessRecovery: true, layers: count, reference: await h.referenceState(page), controlsWork: true };
}
