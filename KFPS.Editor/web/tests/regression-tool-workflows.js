async page => {
  const check = (ok, message) => { if (!ok) throw new Error(message); };
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
  await page.locator('#selectSameShape').click();
  check(await page.evaluate(() => selectedVinylObjects().length) === 2, 'Same Shape selected the wrong layers');
  await page.locator('#selectInverseLayers').click();
  check(await page.evaluate(() => selectedVinylObjects().length === 1 && selectedVinylObjects()[0] === vinylObjects()[1]), 'Invert selected the wrong layers');
  await page.locator('#clearLayerSelection').click();
  check(await page.evaluate(() => !selectedVinylObjects().length), 'Clear selection failed');
  await page.evaluate(() => { canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel(); });
  await page.locator('#selectSameColor').click();
  check(await page.evaluate(() => selectedVinylObjects().length) === 2, 'Same Color selected the wrong layers');

  for (const direction of ['left', 'centerX', 'right', 'top', 'centerY', 'bottom']) {
    await setup(); await page.locator('#selectAllLayers').click();
    await page.locator(`[data-align="${direction}"]`).click();
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
    await setup(); await page.locator('#selectAllLayers').click();
    await page.locator(`#distribute${axis}`).click();
    check(await page.evaluate(axis => {
      const values = vinylObjects().map(object => object.getCenterPoint()[axis === 'Horizontal' ? 'x' : 'y']).sort((a, b) => a - b);
      return Math.abs(values[1] - values[0] - (values[2] - values[1])) < .01;
    }, axis), `Distribution failed: ${axis}`);
  }
  await setup();
  const before = await page.evaluate(() => JSON.stringify(snapshotShapes()));
  for (const button of ['flipHorizontal', 'flipHorizontal', 'flipVertical', 'flipVertical', 'rotateRight', 'rotateLeft']) await page.locator(`#${button}`).click();
  check(await page.evaluate(before => JSON.stringify(snapshotShapes()) === before, before), 'Reversible transform buttons changed artwork');
  await page.locator('#maskSelectedTool').click();
  check(await page.evaluate(() => vinylObjects()[0].kloudy.mask), 'Mask button failed');
  await page.locator('#maskSelectedTool').click();
  check(await page.evaluate(() => !vinylObjects()[0].kloudy.mask), 'Mask button failed to revert');

  await page.locator('#helpBtn').click();
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
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Tool workflow persistence');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()));
  check(await page.evaluate(() => favorites.has('Primitives:1')), 'Real shape favorite did not survive reload');
  await page.screenshot({ path: 'tool-workflows.png' });
  return { modes, selection: true, alignments: 6, distributions: 2, reversibleTransforms: true,
    maskToggle: true, help: true, shapeSearch: true, keyboardFavorite: true, favoriteReload: true };
}
