async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const count = options.large ? 2400 : 400;
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const command = async id => {
    const menu = await page.locator(`#${id}`).evaluate(button => button.closest('.workspaceMenu')?.id);
    if (menu) await page.locator(`[aria-controls="${menu}"]`).click();
    await page.locator(`#${id}`).click();
  };
  await page.setViewportSize({ width: 1600, height: 1000 });
  if (options.workspaceRestart) {
    const state = await page.evaluate(() => ({ settings: readDockState(), hidden: document.querySelector('.workspace').classList.contains('dockCollapsed'),
      panel: document.querySelector('.inspectorDock .dockTab.active').dataset.panel, layers: vinylObjects().length }));
    check(state.settings.width === 432 && state.settings.layerPercent === 51 && state.settings.hidden && state.hidden,
      'Dock dimensions or hidden state did not survive a new Windows host: ' + JSON.stringify(state));
    check(state.panel === 'historyPane' && state.layers === count, 'Panel or saved document did not resume');
    await command('workspaceReset');
    await page.evaluate(() => KfpsEditorPreferences.flush());
    return { passed: true, freshProcessRestart: state, reset: true };
  }
  const fixture = path.join(output, 'workspace-controls.json');
  fs.writeFileSync(fixture, JSON.stringify({ shapes: Array.from({ length: count }, (_, index) => ({
    type: [1048677, 1048678, 1048679][index % 3], color: [60, 160, 190, 255],
    data: [-550 + index % 30 * 35, 500 - Math.floor(index / 30) * 40, .2, .2, index % 4 * 15, 0, 0],
    editor_id: `workspace-control-${index}`, shape_name: `Shape ${index}`,
    ...(index >= count - 48 ? { editor_group_id: 'dense-batch', editor_group_name: 'Dense batch' } : {}),
  })) }));
  await h.fileInput(page, '#jsonInput', fixture);
  await page.waitForFunction(count => vinylObjects().length === count && !recoveryRestoreDepth, count);
  await page.locator('#workspaceFit').click();
  console.log('workspace-controls: input loaded');
  const original = await h.snapshot(page);
  await h.select(page, 'Dense batch', true);
  await page.locator('#quickFitSelected').click();
  check(await page.evaluate(() => selectedVinylObjects().length) === 48, 'Group row did not select its members');
  const outside = shapes => JSON.stringify(JSON.parse(shapes).filter(shape => shape.editor_group_id !== 'dense-batch'));
  const actions = [];
  for (const kind of (options.skipTransforms ? [] : ['move', 'side', 'corner', 'rotate'])) {
    const geometry = await h.geometry(page);
    let from, to;
    if (kind === 'move') { from = geometry.grab; to = { x: from.x + 24, y: from.y + 15 }; }
    if (kind === 'side') { from = geometry.handles.mr; to = { x: from.x + 25, y: from.y }; }
    if (kind === 'corner') { from = geometry.handles.br; to = { x: from.x + 20, y: from.y + 15 }; }
    if (kind === 'rotate') { from = geometry.handles.mtr; to = { x: from.x + 50, y: from.y + 8 }; }
    await page.mouse.move(from.x, from.y); await page.mouse.down();
    await page.mouse.move(to.x, to.y, { steps: 2 }); await page.mouse.up();
    const changed = await h.snapshot(page);
    check(changed !== original, `${kind} did not change the selected group`);
    check(outside(changed) === outside(original), `${kind} changed unrelated layers`);
    await h.undo(page, original);
    await page.locator('#redoBtn').click(); await page.waitForFunction(() => !editorCommands.busy);
    check(await h.snapshot(page) === changed, `${kind} redo was not exact`);
    await h.undo(page, original);
    await h.select(page, 'Dense batch', true);
    actions.push(kind);
    console.log(`workspace-controls: ${kind} passed`);
  }
  console.log(options.skipTransforms ? 'workspace-controls: separate continuation qualification' : 'workspace-controls: pointer transforms and exact undo/redo passed');
  await page.locator('[data-tool-mode="select"]').click();
  await page.locator('#quickColorSwatch').click();
  await page.locator('#dialogColorPicker').fill('#18b6aa');
  await page.locator('#closeColorDialog').click();
  await page.locator('#applyColorToSelection').click();
  check(await page.evaluate(() => selectedVinylObjects().every(object => {
    const color = objectToShape(object).color; return color[0] === 24 && color[1] === 182 && color[2] === 170;
  })), 'Batch colour did not apply to selected shapes');
  check(outside(await h.snapshot(page)) === outside(original), 'Recolour changed unrelated layers');
  await h.undo(page, original);
  console.log('workspace-controls: batch recolour and undo passed');
  await page.locator('#layerSearch').fill('');
  await page.locator('#workspaceFit').click();
  const zoom = await page.evaluate(() => canvas.getZoom());
  await page.locator('#workspaceZoomIn').click();
  check(await page.evaluate(() => canvas.getZoom()) > zoom, 'Zoom in did not zoom');
  await page.locator('#workspaceZoomOut').click();
  check(Math.abs(await page.evaluate(() => canvas.getZoom()) - zoom) < 1e-8, 'Zoom out did not restore scale');
  const bounds = await page.locator('.upper-canvas').boundingBox();
  for (const button of ['middle', 'right']) {
    const before = await page.evaluate(() => canvas.viewportTransform.slice());
    await page.mouse.move(bounds.x + 100, bounds.y + 100); await page.mouse.down({ button });
    await page.mouse.move(bounds.x + 135, bounds.y + 120, { steps: 2 }); await page.mouse.up({ button });
    check(await page.evaluate(before => canvas.viewportTransform[4] !== before[4] && !isPanning, before), `${button} pan did not finish`);
  }
  check(await h.snapshot(page) === original, 'Navigation changed artwork');
  console.log('workspace-controls: pan and zoom passed');
  await page.locator('#workspaceEditMenu').click();
  for (const key of ['ArrowDown', 'ArrowUp', 'End', 'Home']) await page.keyboard.press(key);
  await page.keyboard.press('Escape');
  check(await h.snapshot(page) === original, 'Menu navigation nudged artwork');
  check(await page.locator('#workspaceEditMenu').evaluate(node => node === document.activeElement), 'Escape lost menu trigger focus');
  await command('startEditorTour');
  const tour = [];
  for (let index = 0; index < 12; index++) {
    const target = await page.evaluate(() => {
      const node = document.querySelector('.editorTourTarget'), rect = node?.getBoundingClientRect();
      return { title: $('editorTourTitle').textContent, visible: !!rect?.width && !!rect?.height,
        card: $('editorTourCard').getBoundingClientRect().toJSON() };
    });
    check(target.visible && target.card.bottom <= 1000, 'Tour targeted a hidden/offscreen control');
    tour.push(target.title); await page.locator('#editorTourNext').click();
    console.log(`workspace-controls: tour step ${index + 1} passed`);
  }
  check(await page.locator('#editorTourLayer').isHidden(), 'Tour did not finish');
  check(await h.snapshot(page) === original, 'Tour changed artwork');
  await command('workspaceReset');
  await command('saveProjectAs');
  await page.locator('#textPromptInput').fill('Workspace workflow');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await command('newCanvas');
  await page.waitForFunction(() => vinylObjects().length === 0);
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({ has: page.getByText('Workspace workflow', { exact: true }) }).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(count => vinylObjects().length === count && !recoveryRestoreDepth && !documentDirty, count);
  check(await h.snapshot(page) === original, 'Saved project did not reopen exactly');
  console.log('workspace-controls: exact save and reopen passed');
  const divider = page.locator('#workspaceDockWidth');
  await divider.focus(); await divider.press('ArrowLeft'); await divider.press('ArrowLeft'); await divider.press('ArrowLeft');
  await page.locator('#dockSplitter').focus(); await page.locator('#dockSplitter').press('ArrowDown');
  await page.locator('[data-panel="historyPane"]').click();
  await command('toggleRightDock');
  const state = await page.evaluate(() => readDockState());
  check(state.width === 432 && state.layerPercent === 51 && state.hidden, 'Layout preferences were not saved');
  await page.evaluate(async () => { await KfpsEditorPreferences.flush(); await flushPendingAutosave(); });
  return { passed: true, layers: count, groupMembers: 48, transforms: actions, exactUndoRedo: !options.skipTransforms,
    recolour: true, panZoom: true, menuIsolation: true, tour, exactSaveReopen: true, restartState: state };
}
