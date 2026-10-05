async (page) => {
  page.setDefaultTimeout(30000);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  await page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_, i) => ({
      type: 1048677, color: [80, 160, 220, i % 3 ? 255 : 100],
      data: [-850 + i % 60 * 28, 620 - Math.floor(i / 60) * 25, .2, .15, i % 90, 0, 0],
      editor_id: `focus-${i}`, shape_name: `Focus test ${i}`,
      editor_locked: i === 2997, editor_hidden: i === 2996,
      editor_group_id: i >= 2990 && i <= 2994 ? 'focus-inner' : null,
      editor_group_name: i >= 2990 && i <= 2994 ? 'Focus inner' : null,
      editor_group_path: i >= 2990 && i <= 2994
        ? [{ id: 'focus-outer', name: 'Focus outer' }, { id: 'focus-inner', name: 'Focus inner' }] : null,
    }));
    shapes[10].editor_group_id = 'focus-single';
    shapes[10].editor_group_name = 'One member';
    await loadPayload({ shapes });
    const target = vinylObjects()[2998];
    target.set({ skewX: 23, flipX: true }); target.setCoords();
    activateDockPanel('layersPane'); refreshLayers();
    window.__focusBefore = JSON.stringify(snapshotShapes());
    window.__focusHistory = editorHistory.index;
    window.__focusDirty = documentDirty;
    window.__focusEvents = [];
    document.getElementById('layers').addEventListener('dblclick', event => {
      __focusEvents.push({ trusted: event.isTrusted, control: isLayerControlTarget(event.target) });
    }, true);
  });
  const row = async (id) => {
    const key = await page.evaluate(id => {
      const key = id.startsWith('group:') ? id : layerListObjectKey(vinylObjects().find(o => o.kloudy.editor_id === id));
      const index = layerListEntries.findIndex(entry => entry.key === key);
      if (index < 0) throw Error(`Missing row: ${id}`);
      layerScrollPane().scrollTop = index * 62;
      renderVirtualLayerWindow(true);
      return key;
    }, id);
    const element = page.locator(`[data-layer-list-key="${key}"]`);
    return element;
  };
  const resetView = async (zoom = .4) => page.evaluate(zoom => {
    canvas.setViewportTransform([zoom, 0, 0, zoom, -6500, 8500]);
    canvas.requestRenderAll();
  }, zoom);
  const measure = () => page.evaluate(() => {
    const selected = canvas.getActiveObject(), center = selected.getCenterPoint();
    const screen = fabric.util.transformPoint(center, canvas.viewportTransform);
    return { dx: screen.x - canvas.width / 2, dy: screen.y - canvas.height / 2,
      zoom: canvas.getZoom(), ids: selectedVinylObjects().map(o => o.kloudy.editor_id),
      outline: selectedShapeOutlineHelpers.size, locked: !!selected.kloudy?.locked,
      visible: selected.visible, border: selected.hasBorders,
      rows: document.querySelectorAll('#layers > li').length,
      unchanged: JSON.stringify(snapshotShapes()) === __focusBefore,
      historyUnchanged: editorHistory.index === __focusHistory, dirtyUnchanged: documentDirty === __focusDirty };
  });
  const cases = [];
  for (const [id, zoom] of [['focus-2999', .08], ['focus-2998', 3], ['focus-2997', 1],
    ['focus-2996', .4], ['focus-2992', 2], ['focus-1500', 12], ['focus-0', .2]]) {
    await resetView(zoom);
    const element = await row(id);
    const title = element.locator(id.startsWith('group:') ? '.layerGroupTitle' : '.layerMain b');
    await title.click();
    check(await page.evaluate(() => canvas.viewportTransform[4] === -6500), 'Single click moved the view');
    await title.dblclick({ delay: 90 });
    const state = await measure();
    check(Math.abs(state.dx) < .01 && Math.abs(state.dy) < .01, `${id} was not centered: ${JSON.stringify(state)}`);
    check(state.zoom === zoom && state.unchanged && state.historyUnchanged && state.dirtyUnchanged, `${id} changed document or zoom`);
    check(id.startsWith('group:') ? state.ids.length === 5 : state.ids.join() === id, `${id} selected wrong layers`);
    check(state.border !== false && (state.ids.length > 1 || state.outline === 1), `${id} lost selection highlight`);
    if (id === 'focus-2997') check(state.locked, 'Navigation unlocked a layer');
    if (id === 'focus-2996') check(state.visible === false, 'Navigation revealed a hidden layer');
    check(state.rows < 50, 'Navigation devirtualized the list');
    cases.push({ id, ...state });
  }
  await page.screenshot({ path: path.join(output, 'centered-layer.png') });
  for (const [key, count] of [['group:focus-inner', 5], ['group:focus-outer', 5], ['group:focus-single', 1]]) {
    await resetView();
    await (await row(key)).locator('.layerGroupTitle').dblclick({ delay: 90 });
    check(await page.evaluate(count => canvas.viewportTransform[4] === -6500
      && selectedVinylObjects().length === count, count), 'Group double-click moved view or changed group selection');
  }
  // Remount the same row through search, then repeatedly exercise real double-clicks.
  await page.locator('#layerSearch').fill('Focus test 2998');
  for (let i = 0; i < 15; i++) {
    await resetView(i % 2 ? .25 : 2);
    await page.locator('#layers .layerMain b').dblclick({ delay: i % 2 ? 180 : 30 });
    const state = await measure();
    check(Math.abs(state.dx) < .01 && Math.abs(state.dy) < .01 && state.unchanged && state.historyUnchanged,
      'Repeated/search double-click regressed');
  }
  for (const modifier of ['Control', 'Shift', 'Alt', 'Meta']) {
    await resetView();
    await page.locator('#layers .layerMain b').dblclick({ modifiers: [modifier] });
    check(await page.evaluate(() => canvas.viewportTransform[4] === -6500), `${modifier} double-click moved view`);
  }
  await resetView();
  await page.locator('#layers .layerVisibility').dblclick({ delay: 80 });
  check(await page.evaluate(() => canvas.viewportTransform[4] === -6500), 'Visibility control centered view');
  await page.locator('#layers .layerLock').dblclick({ delay: 80 });
  check(await page.evaluate(() => canvas.viewportTransform[4] === -6500), 'Lock control centered view');
  await page.locator('#layerSearch').fill('');
  const grouped = await row('focus-2992');
  await grouped.locator('.layerGroupBadge').dblclick({ delay: 80 });
  check(await page.evaluate(() => canvas.viewportTransform[4] === -6500), 'Group badge centered view');
  await page.locator('#layerSearch').fill('Focus test 2998');
  await resetView();
  const titleBox = await page.locator('#layers .layerMain b').boundingBox();
  const x = titleBox.x + titleBox.width / 2, y = titleBox.y + titleBox.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down({ clickCount: 1 });
  await page.mouse.move(x + 8, y);
  await page.mouse.move(x, y);
  await page.mouse.up({ clickCount: 1 });
  await page.mouse.down({ clickCount: 2 });
  await page.mouse.up({ clickCount: 2 });
  check(await page.evaluate(() => canvas.viewportTransform[4] === -6500), 'Drag followed by click centered view');
  await page.locator('#layers .layerMain b').dblclick();
  check(Math.abs((await measure()).dx) < .01, 'Drag suppression blocked the next ordinary double-click');
  await page.locator('#layerSearch').fill('');
  const events = await page.evaluate(() => __focusEvents);
  check(events.filter(e => e.trusted && !e.control).length >= 24, 'Test did not deliver native double-clicks');
  // Finish on a visible individual shape and persist the disposable test project.
  await resetView(2);
  await (await row('focus-2998')).locator('.layerMain b').dblclick();
  await page.locator('#saveProject').click();
  await page.locator('#textPromptInput').fill('Layer double-click test');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  return { cases, repeatedClicks: 15, groupsDoNotCenter: true, modifiedClicksIgnored: true, controlsIgnored: true, dragClicksIgnored: true,
    trustedDoubleClicks: events.filter(e => e.trusted).length, nativeSave: true };
}
