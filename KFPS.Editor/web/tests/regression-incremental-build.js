async (page, options) => {
  if (!options.reference || !options.recipe) throw Error('This opt-in study requires a local reference and recipe');
  const recipe = JSON.parse(fs.readFileSync(options.recipe, 'utf8'));
  if (!Array.isArray(recipe.phases) || !recipe.phases.length) throw Error('Missing construction phases');
  const ledger = [];
  const record = async (phase, extra = {}) => {
    const state = await page.evaluate(() => ({ layers: vinylObjects().length,
      selected: selectedVinylObjects().length, dirty: documentDirty,
      reference: !!editorReference.image, order: overlayLayerMode }));
    ledger.push({ phase, ...state, ...extra });
    fs.writeFileSync(path.join(output, 'construction-ledger.json'), JSON.stringify(ledger, null, 2));
  };
  const field = async (id, value) => {
    const input = page.locator(`#${id}`);
    await input.fill(String(value)); await input.press('Enter');
    if (await input.getAttribute('aria-invalid') === 'true') throw Error(`Rejected ${id}=${value}`);
  };
  const order = async value => {
    await page.locator('[data-tool-mode="overlay"]').click();
    await page.locator('#overlayLayerMode').selectOption(value);
  };
  const add = async shape => {
    const count = await page.evaluate(() => vinylObjects().length);
    await page.locator('[data-tool-mode="shapeLibrary"]').click();
    await page.locator('#shapeFamily').selectOption('Primitives');
    await page.locator('#shapeSearch').fill('');
    await page.locator('#shapeGrid .shapeTile').nth(shape.index - 1).locator('img').click();
    await page.waitForFunction(count => vinylObjects().length === count + 1 && selectedVinylObjects().length === 1, count);
    await page.locator('[data-panel="propertiesPane"]').click();
    const unit = await page.evaluate(() => {
      const object = selectedVinylObjects()[0];
      const data = objectToShape(object).data;
      return { width: object.width * Math.abs(object.scaleX), height: object.height * Math.abs(object.scaleY), sx: data[2], sy: data[3] };
    });
    const scale = 1800 / recipe.height;
    for (const [id, value] of [
      ['xInput', (shape.x - recipe.width / 2) * scale],
      ['yInput', (recipe.height / 2 - shape.y) * scale],
      ['sxInput', unit.sx * shape.width * scale / unit.width],
      ['syInput', unit.sy * shape.height * scale / unit.height],
      ['rotInput', shape.angle || 0],
    ]) await field(id, Number(value.toFixed(5)));
    // Color uses the real input/change handlers; it is not an OS color-dialog test.
    await page.locator('#colorPicker').evaluate((input, color) => {
      input.value = color;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, shape.color);
    await page.locator('#applyColorToSelection').click();
    await page.waitForFunction(() => !editorCommands.busy);
    await page.evaluate(({ width, height }) => {
      const object = selectedVinylObjects()[0];
      if (Math.abs(object.width * Math.abs(object.scaleX) - width) > .05 ||
          Math.abs(object.height * Math.abs(object.scaleY) - height) > .05) throw Error('Constructed shape dimensions differ from recipe');
    }, { width: shape.width * scale, height: shape.height * scale });
  };
  const checkpoint = async name => {
    await order('below');
    await page.locator('#fitView').click();
    const result = await page.evaluate(async () => {
      const start = performance.now();
      await flushPendingAutosave();
      const recovered = await readAutosavePayload();
      if (JSON.stringify(recovered.shapes) !== JSON.stringify(snapshotShapes())) throw Error('Recovery differs from constructed shapes');
      return { recoveryWaitMs: performance.now() - start, exactRecovery: true };
    });
    await record(name, result);
    await page.screenshot({ path: path.join(output, `construction-${name}.png`) });
  };
  await page.setViewportSize({ width: 1600, height: 1000 });
  if (await page.evaluate(() => vinylObjects().length)) throw Error('Construction requires a fresh empty test profile');
  await page.locator('#overlayInput').setInputFiles(options.reference);
  await page.waitForFunction(() => editorReference.image && !recoveryRestoreDepth);
  await order('above');
  for (let phase = 0; phase < recipe.phases.length; phase++) {
    const entry = recipe.phases[phase];
    for (let index = 0; index < entry.shapes.length; index++) {
      if (index % 8 === 0) await order(index % 16 ? 'below' : 'above');
      await add(entry.shapes[index]);
    }
    await checkpoint(entry.name);
  }
  const artCount = await page.evaluate(() => vinylObjects().length);
  for (const shape of recipe.pattern) await add(shape);
  await page.locator('#selectSameColor').click();
  if (await page.evaluate(() => selectedVinylObjects().length) !== recipe.pattern.length) throw Error('Pattern selection includes unrelated artwork');
  await page.locator('#groupSelected').click();
  await page.locator('#renameSelectedGroup').click();
  await page.locator('#textPromptInput').fill('Repeated hatch study');
  await page.locator('#textPromptInput').press('Enter');
  const expected = artCount + recipe.pattern.length * recipe.patternCopies;
  for (let copy = 1; copy < recipe.patternCopies; copy++) {
    const before = await page.evaluate(() => vinylObjects().length);
    await page.locator('#duplicateLayer').click();
    await page.waitForFunction(expected => vinylObjects().length === expected, before + recipe.pattern.length);
    // Normal grouped duplication and keyboard translation, not synthetic scene load.
    await page.locator('#duplicateLayer').press(copy % 10 ? 'Shift+ArrowRight' : 'Shift+ArrowDown');
    if (copy % 10 === 0) {
      await order(copy % 20 ? 'above' : 'below');
      await record(`pattern-${copy + 1}`);
    }
  }
  if (await page.evaluate(() => vinylObjects().length) !== expected) throw Error('Incremental layer count is wrong');
  await checkpoint('dense');
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Incremental reference study');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  const snapshot = await page.evaluate(() => snapshotShapes());
  fs.writeFileSync(path.join(output, 'expected-shapes.json'), JSON.stringify(snapshot));
  await page.locator('#newCanvas').click();
  await page.waitForFunction(() => vinylObjects().length === 0);
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({ has: page.getByText('Incremental reference study', { exact: true }) }).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(() => !recoveryRestoreDepth && vinylObjects().length > 0 && !!editorReference.image && !documentDirty);
  const reopened = await page.evaluate(() => snapshotShapes());
  if (JSON.stringify(snapshot) !== JSON.stringify(reopened)) throw Error('Project reopened with changed construction');
  await record('saved-reopened', { exact: true });
  return { independentShapes: artCount, patternShapes: recipe.pattern.length,
    patternCopies: recipe.patternCopies, layers: expected, phases: ledger,
    inputLevel: 'Real tiles, field keys, buttons and grouped duplication; color input events; read-only scene assertions' };
}
