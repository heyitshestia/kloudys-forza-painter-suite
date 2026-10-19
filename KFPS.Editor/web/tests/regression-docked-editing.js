async (page) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const choose = async (id, action) => {
    await page.locator('#workspaceViewMenu').click();
    await page.locator('#workspacePanels').click();
    await page.locator(`[data-show-panel="${id}"]`).click();
    if (id === 'layersPane' && await page.locator('.layersDock #layersPane').count()) await page.locator('#workspaceLayerPanelOptions').click();
    else await page.locator(`.dockTab[data-panel="${id}"]`).click({ button: 'right' });
    await page.locator(`[data-dock-action="${action}"]`).click();
  };
  await page.setViewportSize({ width: 1600, height: 1000 });
  page.setDefaultTimeout(15000);
  const input = path.join(output, 'docked-editing.json');
  fs.writeFileSync(input, JSON.stringify({ shapes: Array.from({ length: 12 }, (_, i) => ({
    type: 1048678, color: [40, 150, 170, 255], data: [-300 + i * 55, 0, .3, .3, 0, 0, 0],
    editor_id: `dock-${i}`, shape_name: `Panel shape ${i}`,
  })) }));
  await h.fileInput(page, '#jsonInput', input);
  await page.waitForFunction(() => vinylObjects().length === 12);
  await choose('propertiesPane', 'left');
  await choose('layersPane', 'float');
  await page.locator('[data-panel="layersPane"]').focus();
  await page.keyboard.press('Alt+ArrowRight');
  await h.select(page, 'Panel shape 3');
  const before = await h.snapshot(page);
  await page.locator('#xInput').fill('125'); await page.locator('#xInput').press('Enter');
  await page.waitForFunction(() => Math.abs(objectToShape(selectedVinylObjects()[0]).data[0] - 125) < .001);
  check((await page.locator('.workspaceLeftDock #xInput').count()) === 1, 'Edited input did not stay in left dock');
  await h.undo(page, before);
  await page.locator('#redoBtn').click(); await page.waitForFunction(() => !editorCommands.busy);
  const edited = await h.snapshot(page);
  check(edited !== before, 'Detached property edit was not redoable');
  await choose('propertiesPane', 'float');
  await page.locator('#rotInput').fill('30'); await page.locator('#rotInput').press('Enter');
  await page.waitForFunction(() => Math.abs(objectToShape(selectedVinylObjects()[0]).data[4] - 30) < .001);
  await h.undo(page, edited);
  await choose('layersPane', 'home');
  await choose('propertiesPane', 'left');
  await page.locator('#workspaceViewMenu').click();
  await page.locator('#editorThemeSelect').selectOption('dark'); await page.keyboard.press('Escape');
  await page.locator('#workspaceFileMenu').click(); await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Docked editing'); await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !documentDirty && !projectSaveInProgress);
  await page.locator('#workspaceFileMenu').click(); await page.locator('#newCanvas').click();
  await page.waitForFunction(() => vinylObjects().length === 0);
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({ has: page.getByText('Docked editing', { exact: true }) }).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(() => vinylObjects().length === 12 && !recoveryRestoreDepth);
  check(await h.snapshot(page) === edited, 'Docked project save/reopen changed artwork');
  await page.locator('#layerSearch').fill(''); await page.locator('#workspaceFit').click();
  await page.mouse.move(600, 980);
  await page.screenshot({ path: path.join(output, 'docked-editing.png') });
  return { passed: true, layers: 12, floatingLayerSelection: true, leftNumericEdit: true,
    floatingNumericEdit: true, exactUndoRedo: true, exactSaveReopen: true };
}
