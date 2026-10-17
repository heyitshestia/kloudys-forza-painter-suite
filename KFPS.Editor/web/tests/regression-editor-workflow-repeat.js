async page => {
  page.setDefaultTimeout(20000);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const idle = () => page.waitForFunction(() => !editorCommands.busy && !projectSaveInProgress);
  const blur = () => page.evaluate(() => document.activeElement?.blur());
  const snapshot = () => page.evaluate(() => JSON.stringify(snapshotShapes()));
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 12 }, (_, i) => ({
      type: 1048677, data: [i * 120 - 600, 0, .3, .3, 0, 0, 0], color: [50, 120, 180, 255],
      editor_id: `repeat-${i}`, editor_locked: i === 0,
      ...(i < 2 ? { editor_group_id: 'child', editor_group_name: 'Child',
        editor_group_path: [{ id: 'parent', name: 'Parent' }, { id: 'child', name: 'Child' }] }
        : i === 2 ? { editor_group_id: 'parent', editor_group_name: 'Parent' } : {})
    })) });
    favoriteColors = Array.from({ length: 16 }, (_, i) => [i * 12, 80, 160, 255]);
    saveFavoriteColors(); resetShortcuts();
    selectObjects([vinylObjects()[11]], 'test');
  });
  // Existing user bindings must win in the real keyboard path, not only in loading.
  await page.evaluate(() => {
    editorSettings.setItem(SHORTCUTS_KEY, JSON.stringify({ duplicate: '1' }));
    shortcuts = loadShortcuts(); updateShortcutLabels();
  });
  await blur();
  const legacyBefore = await snapshot();
  await page.keyboard.press('1'); await idle();
  check(await page.evaluate(() => vinylObjects().length === 13 && shortcuts.colorSlot1 === ''), 'Legacy shortcut did not retain priority');
  await page.locator('#undoBtn').click(); await idle();
  check(await snapshot() === legacyBefore, 'Legacy shortcut undo mismatch');
  await page.evaluate(() => resetShortcuts());
  await page.locator('#shortcutsBtn').click();
  await page.locator('[data-shortcut-action="colorSlot1"]').click();
  await page.keyboard.press('Control+c');
  check(await page.evaluate(() => shortcutFor('copy') === 'Ctrl+C' && shortcutFor('colorSlot1') === '1'), 'Conflicting binding was accepted');
  await page.keyboard.press('Escape');
  // Empty reference toggles must be safe; bulk colour changes respect locked members.
  await blur(); await page.keyboard.press('Space');
  check(await snapshot() === legacyBefore, 'Empty reference toggle changed the document');
  await page.evaluate(() => {
    selectObjects(vinylObjects().slice(0, 3), 'test');
  });
  const colorBefore = await snapshot();
  await blur(); await page.keyboard.press('4');
  check(await page.evaluate(() => {
    const objects = vinylObjects(), color = favoriteColors[3];
    return JSON.stringify(objectToShape(objects[0]).color) === JSON.stringify([50, 120, 180, 255])
      && objects.slice(1, 3).every(object => JSON.stringify(objectToShape(object).color) === JSON.stringify(color));
  }), 'Mixed locked/unlocked colour selection failed');
  await page.locator('#undoBtn').click(); await idle();
  check(await snapshot() === colorBefore, 'Bulk colour undo mismatch');
  // Repeated membership edits must not accumulate wrappers or damage undo history.
  const membershipBefore = await snapshot();
  for (let i = 0; i < 12; i++) {
    await page.evaluate(() => selectObjects([vinylObjects()[11]], 'test'));
    await page.locator('#groupActions').click(); await page.locator('#addSelectedToGroup').click();
    await page.locator('#addToGroupTarget').selectOption('child');
    await page.locator('#addToGroupDialog button[value=add]').click();
    check(await page.evaluate(() => KfpsEditorLayerGroups.objectPath(vinylObjects()[11]).map(g => g.id).join('/') === 'parent/child'), 'Repeated grouping changed target ancestry');
    await page.locator('#undoBtn').click(); await idle();
    check(await snapshot() === membershipBefore, 'Repeated membership undo drifted');
  }
  // A stale dialog must never apply its saved selection to a replacement document.
  await page.evaluate(() => selectObjects([vinylObjects()[11]], 'test'));
  await page.locator('#groupActions').click(); await page.locator('#addSelectedToGroup').click();
  await page.evaluate(async () => {
    await loadPayload({ shapes: [{ type: 1048678, data: [0, 0, 1, 1, 0, 0, 0], color: [100, 180, 50, 255], editor_id: 'replacement' }] });
  });
  const replacement = await snapshot();
  await page.locator('#addToGroupDialog button[value=add]').click();
  check(await snapshot() === replacement, 'Stale group dialog changed replacement artwork');
  // Real double-clicks must reopen hidden/collapsed docks and reveal the selected row.
  for (const mode of ['hidden', 'collapsed']) {
    await page.evaluate(mode => {
      setDockVisible(mode !== 'hidden'); setLayersCollapsed(mode === 'collapsed');
      $('layerSearch').value = 'missing'; refreshLayers(); setToolRailMode('select');
    }, mode);
    await page.waitForTimeout(120);
    const point = await page.evaluate(() => {
      canvas.setZoom(1); centerCanvasOnObject(vinylObjects()[0]);
      const rect = canvas.upperCanvasEl.getBoundingClientRect(), dock = document.querySelector('.rightDock').getBoundingClientRect();
      const visibleWidth = document.querySelector('.workspace').classList.contains('dockCollapsed')
        ? rect.width : Math.min(rect.width, dock.left - rect.left);
      const x = Math.max(60, visibleWidth / 2), y = rect.height / 2;
      canvas.relativePan(new fabric.Point(x - rect.width / 2, 0));
      return { x: rect.left + x, y: rect.top + y, hittable: document.elementFromPoint(rect.left + x, rect.top + y) === canvas.upperCanvasEl };
    });
    check(point.hittable, `Canvas click is covered in ${mode} layout`);
    await page.mouse.dblclick(point.x, point.y, { delay: 80 });
    await page.waitForFunction(() => {
      const row = document.querySelector('#layers .layerLocated');
      return row && row.getBoundingClientRect().height > 0 && !$('layerSearch').value
        && !document.querySelector('.workspace').classList.contains('dockCollapsed')
        && !document.querySelector('.rightDock').classList.contains('layersCollapsed');
    });
    check(await snapshot() === replacement, 'Dock reveal changed artwork');
  }
  await page.evaluate(() => { canvas.discardActiveObject(); updateSelectionPanel(); refreshLayers(); });
  check(await page.evaluate(() => !locatedLayerListKey && !document.querySelector('#layers .layerLocated')), 'Located highlight survived clearing selection');
  // Toggle a real reference repeatedly without replacing the image or losing properties.
  await page.evaluate(() => activateDockPanel('overlayPane'));
  const png = await page.evaluate(() => {
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const context = c.getContext('2d'); context.fillStyle = '#df8040'; context.fillRect(0, 0, 64, 64);
    return c.toDataURL().split(',')[1];
  });
  await page.locator('#overlayInput').setInputFiles({ name: 'repeat-reference.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await page.waitForFunction(() => !!editorReference.image);
  const reference = await page.evaluate(() => {
    window.__repeatReference = editorReference.image;
    return JSON.stringify(editorReference.sourceOverlayProjectState());
  });
  await blur();
  for (let i = 0; i < 30; i++) await page.keyboard.press('Space');
  check(await page.evaluate(reference => editorReference.image === __repeatReference
    && JSON.stringify(editorReference.sourceOverlayProjectState()) === reference, reference), 'Repeated reference toggles lost properties or replaced image');
  await page.locator('#saveProjectAs').click(); await page.locator('#textPromptInput').fill('Repeated workflow regression');
  await page.locator('#textPromptInput').press('Enter'); await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => { await flushPendingAutosave(); await KfpsEditorPreferences.flush(); });
  return { legacyBinding: true, conflictingBindingRejected: true, mixedLockedColors: true,
    membershipUndoCycles: 12, staleDialog: true, dockReveal: ['hidden', 'collapsed'], referenceToggleCycles: 30 };
}
