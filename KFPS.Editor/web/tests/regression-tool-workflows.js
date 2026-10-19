async page => {
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const click = async selector => {
    const control = page.locator(selector);
    const menu = await control.evaluate(node => node.closest('.workspaceMenu')?.id);
    if (menu && !await page.locator(`#${menu}`).evaluate(node => node.matches(':popover-open')))
      await page.locator(`[aria-controls="${menu}"]`).click();
    const disclosure = control.locator('xpath=ancestor::details[1]');
    if (await disclosure.count() && !await disclosure.evaluate(node => node.open))
      await disclosure.locator(':scope > summary').click();
    await control.click();
  };
  await page.setViewportSize({ width: 1600, height: 1000 });
  const setup = () => page.evaluate(async () => {
    await loadPayload({ shapes: [0, 1, 2].map(i => ({ type: i === 1 ? 1048678 : 1048677,
      color: i === 1 ? [180, 80, 30, 255] : [60, 150, 210, 255], data: [[-200, 20, 310][i], i * 120 - 100, .5, .5, 0, 0, 0] })) });
    canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel();
  });
  await setup();
  const modes = await page.locator('.toolButton[data-tool-mode]').evaluateAll(buttons => buttons.map(button => button.dataset.toolMode));
  for (const mode of modes) {
    await page.locator(`.toolButton[data-tool-mode="${mode}"]`).click();
    check(await page.evaluate(mode => activeToolMode === mode, mode), `Tool did not activate: ${mode}`);
  }
  await page.locator('.toolButton[data-tool-mode="select"]').click();
  await setup();
  await click('#selectSameShape');
  check(await page.evaluate(() => selectedVinylObjects().length) === 2, 'Same Shape selected the wrong layers');
  await click('#selectInverseLayers');
  check(await page.evaluate(() => selectedVinylObjects().length === 1 && selectedVinylObjects()[0] === vinylObjects()[1]), 'Invert selected the wrong layers');
  await click('#clearLayerSelection');
  check(await page.evaluate(() => !selectedVinylObjects().length), 'Clear selection failed');
  await page.evaluate(() => { canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel(); });
  await click('#selectSameColor');
  check(await page.evaluate(() => selectedVinylObjects().length) === 2, 'Same Color selected the wrong layers');

  for (const direction of ['left', 'centerX', 'right', 'top', 'centerY', 'bottom']) {
    await setup(); await click('#selectAllLayers');
    await click(`[data-align="${direction}"]`);
    const aligned = await page.evaluate(direction => {
      const values = vinylObjects().map(object => {
        const rect = object.getBoundingRect(true, true);
        return ({ left: rect.left, centerX: rect.left + rect.width / 2, right: rect.left + rect.width,
          top: rect.top, centerY: rect.top + rect.height / 2, bottom: rect.top + rect.height })[direction];
      });
      return Math.max(...values) - Math.min(...values) < .01;
    }, direction);
    check(aligned, `Alignment failed: ${direction}`);
  }
  for (const axis of ['Horizontal', 'Vertical']) {
    await setup(); await click('#selectAllLayers');
    await click(`#distribute${axis}`);
    check(await page.evaluate(axis => {
      const values = vinylObjects().map(object => object.getCenterPoint()[axis === 'Horizontal' ? 'x' : 'y']).sort((a, b) => a - b);
      return Math.abs(values[1] - values[0] - (values[2] - values[1])) < .01;
    }, axis), `Distribution failed: ${axis}`);
  }
  await setup();
  const before = await page.evaluate(() => JSON.stringify(snapshotShapes()));
  for (const button of ['flipHorizontal', 'flipHorizontal', 'flipVertical', 'flipVertical', 'rotateRight', 'rotateLeft']) await click(`#${button}`);
  check(await page.evaluate(before => JSON.stringify(snapshotShapes()) === before, before), 'Reversible transform buttons changed artwork');
  await page.locator('#maskSelectedTool').click();
  check(await page.evaluate(() => vinylObjects()[0].kloudy.mask), 'Mask button failed');
  await page.locator('#maskSelectedTool').click();
  check(await page.evaluate(() => !vinylObjects()[0].kloudy.mask), 'Mask button failed to revert');

  await click('#helpBtn');
  await page.locator('#helpDialog').waitFor({ state: 'visible' });
  await page.locator('#closeHelp').click();
  await page.locator('#helpDialog').waitFor({ state: 'hidden' });
  await page.locator('.toolButton[data-tool-mode="shapeLibrary"]').click();
  await page.locator('#shapeFamily').selectOption('Primitives');
  await page.locator('#shapeSearch').fill('1048677');
  check(await page.locator('#shapeGrid .shapeTile').count() === 1, 'Shape type-code search failed');
  const count = await page.evaluate(() => vinylObjects().length);
  await page.locator('#shapeGrid .favButton').focus();
  await page.keyboard.press('Enter');
  await page.evaluate(() => KfpsEditorPreferences.flush());
  check(await page.evaluate(() => vinylObjects().length) === count, 'Keyboard favorite action inserted a shape');
  check(await page.evaluate(() => favorites.has('Primitives:1')), 'Keyboard favorite action did not save the favorite');
  for (const expected of [false, true]) {
    await page.locator('#shapeGrid .favButton').focus();
    await page.keyboard.press('Space');
    check(await page.evaluate(expected => favorites.has('Primitives:1') === expected, expected), 'Space did not toggle the favorite');
    check(await page.evaluate(() => vinylObjects().length) === count, 'Space on favorite inserted a shape');
  }
  await page.evaluate(() => KfpsEditorPreferences.flush());
  await click('#saveProjectAs');
  await page.locator('#textPromptInput').fill('Tool workflow persistence');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await require(path.join(__dirname, 'chrome-reload-adapter.cjs'))(page, output, () => page.reload());
  check(await page.evaluate(() => favorites.has('Primitives:1')), 'Real shape favorite did not survive reload');
  await page.screenshot({ path: path.join(output, 'tool-workflows.png') });
  return { modes, selection: true, alignments: 6, distributions: 2, reversibleTransforms: true,
    maskToggle: true, help: true, shapeSearch: true, keyboardFavorite: true, favoriteReload: true };
}
