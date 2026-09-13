async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  const initial = options.derived ? await h.setupDerived(page, output, { ...options, layers: 2950 }) : await h.setup(page, output, options);
  await h.saveAs(page, "Selection edge checkpoint");
  const original = await h.snapshot(page), checks = [];
  const state = () => page.evaluate(() => ({
    selected: selectedVinylObjects().length,
    info: document.getElementById("layerInfo").textContent,
    emptyInfo: KfpsI18n.t("{0} editable layer(s). Export writes bottom-to-top order.", vinylObjects().length),
    history: editorHistory.index, dirty: documentDirty,
  }));
  for (const language of options.bothLanguages ? ["en", "ko"] : ["en"]) {
    if (await page.evaluate(() => KfpsI18n.language) !== language) {
      await page.locator("#editorLanguageSelect").selectOption(language);
      await page.locator("#messageDialog").waitFor({ state: "visible" });
      await page.locator("#messageDialogClose").click();
      await page.reload();
      await page.waitForFunction(({ language, layers }) => KfpsI18n.language === language
        && vinylObjects().length === layers && !recoveryRestoreDepth, { language, layers: initial.layers });
    }
    await page.locator("#selectAllLayers").click();
    await page.locator("#clearLayerSelection").click();
    await page.waitForTimeout(500);
    const cleared = await state();
    checks.push({ name: "clear-selection-hint", language, passed: cleared.selected === 0 && cleared.info === cleared.emptyInfo, state: cleared });
    await page.locator("#selectAllLayers").click();
    await page.locator("#selectInverseLayers").click();
    await page.waitForTimeout(500);
    const inverted = await state();
    checks.push({ name: "invert-full-selection", language, passed: inverted.selected === 0 && inverted.info === inverted.emptyInfo, state: inverted });
    await page.screenshot({ path: path.join(output, `selection-edge-${language}.png`) });
    if (await page.locator("#clearLayerSelection").isEnabled()) await page.locator("#clearLayerSelection").click();
    await page.locator("#selectInverseLayers").click();
    checks.push({ name: "invert-empty-selection", language, passed: (await state()).selected === initial.layers });
    await page.locator("#clearLayerSelection").click();
    checks.push({ name: "selection-does-not-edit", language, passed: await h.snapshot(page) === original && !inverted.dirty && inverted.history === 0 });
  }
  fs.writeFileSync(path.join(output, "selection-edges.json"), JSON.stringify({ initial, checks }, null, 2));
  h.check(checks.every(item => item.passed), checks.filter(item => !item.passed).map(item => item.name).join(", "));
  return { initial, checks };
}
