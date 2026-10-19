async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const cases = {
    'small-narrow': { count: 12, width: 760, height: 640, zoom: .25, batch: 6 },
    'small-wide': { count: 12, width: 1760, height: 1040, zoom: 2, batch: 6 },
    medium: { count: 300, width: 1280, height: 800, zoom: 1, batch: 12 },
    'dense-low': { count: 3000, width: 1280, height: 800, zoom: .25, batch: 48 },
    'dense-wide': { count: 3000, width: 1760, height: 1040, zoom: 1, batch: 48 },
    complex: { count: 300, width: 1760, height: 1040, zoom: 2, batch: 12, complex: true },
  };
  const name = options.saveOnly ? 'save-only' : options.matrixCase || 'small-narrow';
  const config = options.saveOnly ? { width: 1600, height: 1000 } : cases[name];
  if (!config) throw Error(`Unknown matrixCase: ${name}`);
  page.setDefaultTimeout(20000);
  await page.setViewportSize({ width: config.width, height: config.height });
  const check = (condition, message) => { if (!condition) throw Error(message); };
  const save = (file, value) => fs.writeFileSync(path.join(output, file), JSON.stringify(value, null, 2));
  const report = { matrixCase: name, config, actions: [], limitations: 'CDP input in an offscreen/headless host; not physical input or hardware performance.' };
  const idle = () => page.waitForFunction(() => !editorCommands.busy && !projectSaveInProgress && !recoveryRestoreDepth);
  const snapshot = () => h.snapshot(page);
  const shortcutFocus = () => page.evaluate(() => document.activeElement?.blur());
  const step = async (label, action) => {
    const started = Date.now(), entry = { label, passed: false };
    report.actions.push(entry); save('host-editing-matrix.json', report);
    try { entry.result = await action(); entry.passed = true; }
    catch (error) { entry.error = String(error.stack || error); throw error; }
    finally { entry.ms = Date.now() - started; save('host-editing-matrix.json', report); console.log(`host-matrix ${name}: ${label} ${entry.passed ? 'passed' : 'failed'}`); }
  };
  const command = async id => {
    const menu = await page.locator(`#${id}`).evaluate(node => node.closest('.workspaceMenu')?.id);
    if (menu && !await page.locator(`#${menu}`).isVisible()) await page.locator(`[aria-controls="${menu}"]`).click();
    await page.locator(`#${id}`).click();
  };
  const select = async (label, group = false) => {
    await page.locator('[data-tool-mode="select"]').click();
    await h.select(page, label, group);
    await idle();
  };
  const prepareView = async () => {
    await page.evaluate(zoom => {
      const target = canvas.getActiveObject();
      if (!target) throw Error('No selected gesture target');
      const center = target.getCenterPoint();
      const rect = canvas.upperCanvasEl.getBoundingClientRect();
      const dock = document.querySelector('.rightDock').getBoundingClientRect();
      const available = Math.min(rect.width, dock.width ? dock.left - rect.left : rect.width);
      canvas.setViewportTransform([zoom, 0, 0, zoom, available / 2 - center.x * zoom, canvas.height / 2 - center.y * zoom]);
      target.setCoords(); styleActiveTransformControls(); canvas.renderAll();
    }, config.zoom);
    return h.geometry(page);
  };
  const historyCycle = async (before, after, keyboard = false) => {
    if (keyboard) { await shortcutFocus(); await page.keyboard.press('Control+z'); await idle(); }
    else await h.undo(page, before);
    check(await snapshot() === before, 'Undo did not restore exact shapes/order/metadata');
    if (keyboard) { await page.keyboard.press('Control+y'); await idle(); }
    else { await page.locator('#redoBtn').click(); await idle(); }
    check(await snapshot() === after, 'Redo did not restore exact changed state');
    await h.undo(page, before);
  };
  if (!options.saveOnly) {
  await step('real-file-import', async () => {
    const shapes = await page.evaluate(({ count, batch, complex }) => {
      const families = ['Tribal', 'Nature', 'Tears', 'Flames', 'Paint_Splats', 'Racing_Icons', 'Upper_Letters_1', 'Primitives'];
      const slots = [1, 2, 30, 36, 39, 31, 12, 5];
      const background = count - batch - 2, cols = Math.ceil(Math.sqrt(background * 1.5));
      const shapes = Array.from({ length: background }, (_, index) => {
        const family = complex ? (index % 17 === 8 ? 'Gradient_Shapes' : families[Math.floor(index / slots.length) % families.length]) : 'Primitives';
        const slot = complex ? (family === 'Gradient_Shapes' ? 1 : slots[index % slots.length]) : index % 2 + 1;
        const mask = complex && index > 0 && index % 53 === 0;
        return { type: editorCatalog.resourceToTypeCode(family, slot), resource_family: family, resource_index: slot,
          editor_id: `matrix-background-${index}`, shape_name: `Matrix background ${index}`, mask,
          color: [45 + index * 37 % 190, 40 + index * 73 % 190, 50 + index * 23 % 180, index % 3 ? 255 : 151],
          data: [(index % cols - cols / 2) * 22, -200 - Math.floor(index / cols) * 22, .16, .14, index % 6 * 17, 0, mask ? 1 : 0] };
      });
      const columns = Math.min(8, Math.ceil(Math.sqrt(batch * 2)));
      for (let index = 0; index < batch; index++) shapes.push({ type: 1048677 + index % 2,
        editor_id: `matrix-batch-${index}`, shape_name: `Matrix batch ${index}`,
        editor_group_id: 'matrix-batch', editor_group_name: 'Matrix batch',
        color: [210, 80, 130, 255], data: [(index % columns - (columns - 1) / 2) * 18, 70 + Math.floor(index / columns) * 18, .12, .12, 0, 0, 0] });
      for (let index = 0; index < 2; index++) shapes.push({ type: 1048677,
        editor_id: `matrix-target-${index}`, shape_name: `Matrix target ${index ? 'B' : 'A'}`,
        color: [70, 170, 200, 255], data: [index * 180, -40, .8, .7, 0, 0, 0] });
      return shapes;
    }, config);
    const filename = path.join(output, 'matrix-input.json');
    fs.writeFileSync(filename, JSON.stringify({ shapes }));
    await h.fileInput(page, '#jsonInput', filename);
    await page.waitForFunction(count => vinylObjects().length === count && !recoveryRestoreDepth, config.count);
    await page.locator('#workspaceFit').click();
    const scene = await h.scene(page);
    return { ...scene, pathCommands: await page.evaluate(() => vinylObjects().reduce((sum, object) => sum + (object.path?.length || 0), 0)) };
  });
  await step('catalog-add-and-exact-history', async () => {
    const full = await snapshot();
    if (config.count === 3000) {
      await select('Matrix target B'); await shortcutFocus(); await page.keyboard.press('Delete'); await idle();
      check(JSON.parse(await snapshot()).length === 2999, 'Delete did not provide one insertion slot');
    }
    const before = await snapshot();
    await page.locator('[data-tool-mode="shapeLibrary"]').click();
    await page.locator('#shapeSearch').fill('1048677');
    await page.waitForFunction(() => $('shapeGrid').getAttribute('aria-busy') === 'false');
    await page.locator('#shapeGrid .shapeTile .shapeName').first().click(); await idle();
    const after = await snapshot();
    check(JSON.parse(after).length === JSON.parse(before).length + 1, 'Catalog click did not add one shape');
    await historyCycle(before, after);
    if (config.count === 3000) await h.undo(page, full);
    return { added: 1, insertionHeadroomRestored: true };
  });
  for (const [kind, group] of [['move', false], ['side', false], ['corner', false], ['skew', false], ['side', true], ['skew', true]]) {
    await step(`${group ? 'batch' : 'single'}-${kind}-pointer-history`, async () => {
      await select(group ? 'Matrix batch' : 'Matrix target A', group);
      const geometry = await prepareView(), before = await snapshot();
      const ids = await page.evaluate(() => selectedVinylObjects().map(object => object.kloudy.editor_id));
      check(ids.length === (group ? config.batch : 1), 'Wrong gesture selection count');
      const from = kind === 'move' ? geometry.grab : geometry.handles[kind === 'side' ? 'mr' : 'br'];
      const to = { x: from.x + (kind === 'skew' ? 24 : 18), y: from.y + (kind === 'side' ? 0 : kind === 'skew' ? 0 : 13) };
      check(await page.evaluate(({ from, to }) => [from, to].every(point => document.elementFromPoint(point.x, point.y) === canvas.upperCanvasEl), { from, to }), 'Gesture handle or destination is covered/outside canvas');
      const started = Date.now();
      if (kind === 'skew') await page.keyboard.down('Shift');
      try { await page.mouse.move(from.x, from.y); await page.mouse.down(); await page.mouse.move(to.x, to.y, { steps: 2 }); await page.mouse.up(); }
      finally { await page.mouse.up(); if (kind === 'skew') await page.keyboard.up('Shift'); }
      await idle();
      const pointerMs = Date.now() - started, after = await snapshot();
      check(after !== before, 'Pointer gesture did not modify artwork');
      const untouched = text => JSON.stringify(JSON.parse(text).filter(shape => !ids.includes(shape.editor_id)));
      check(untouched(before) === untouched(after), 'Pointer gesture changed unrelated layers');
      const changed = JSON.parse(after).filter(shape => ids.includes(shape.editor_id));
      const prior = new Map(JSON.parse(before).map(shape => [shape.editor_id, shape]));
      check(changed.every(shape => shape.data.every(Number.isFinite) && Math.abs(shape.data[2]) > 1e-6 && Math.abs(shape.data[3]) > 1e-6), 'Gesture produced invalid transform');
      if (kind === 'move') check(changed.some(shape => [0, 1].some(index => shape.data[index] !== prior.get(shape.editor_id).data[index])), 'Move did not translate the selection');
      if (kind === 'side' || kind === 'corner') check(changed.some(shape => [2, 3].some(index => shape.data[index] !== prior.get(shape.editor_id).data[index])), 'Resize did not change selected scale');
      if (kind === 'skew') check(changed.some(shape => Math.abs(shape.data[5]) > .01), 'Shift-corner did not produce serialized skew');
      await historyCycle(before, after);
      return { selected: ids.length, zoom: geometry.zoom, pointerMs, exactUndoRedo: true, unrelatedUnchanged: true };
    });
  }
  await step('batch-recolor-and-history', async () => {
    await select('Matrix batch', true); const before = await snapshot();
    await page.locator('#quickColorSwatch').click();
    await page.locator('#dialogColorPicker').fill('#18b6aa');
    await page.locator('#closeColorDialog').click();
    await page.locator('#applyColorToSelection').click(); await idle();
    const after = await snapshot();
    check(await page.evaluate(() => selectedVinylObjects().every(object => objectToShape(object).color.slice(0, 3).join(',') === '24,182,170')), 'Batch recolor failed');
    check(JSON.stringify(JSON.parse(before).filter(shape => shape.editor_group_id !== 'matrix-batch')) === JSON.stringify(JSON.parse(after).filter(shape => shape.editor_group_id !== 'matrix-batch')), 'Recolor changed unrelated layers');
    await historyCycle(before, after); return { selected: config.batch, exactUndoRedo: true };
  });
  await step('keyboard-nudge-order-and-typing-isolation', async () => {
    await select('Matrix target A');
    for (const key of ['ArrowRight', '[']) {
      const before = await snapshot(); await shortcutFocus(); await page.keyboard.press(key); await idle();
      const after = await snapshot(); check(after !== before, `Shortcut ${key} did nothing`);
      await historyCycle(before, after, true); await select('Matrix target A');
    }
    const before = await snapshot();
    await page.locator('#layerSearch').fill('Matrix target'); await page.locator('#layerSearch').press('ArrowRight');
    check(await snapshot() === before, 'Typing-field arrow nudged artwork');
    await page.locator('#workspaceEditMenu').click(); await page.keyboard.press('ArrowDown'); await page.keyboard.press('Escape');
    check(await snapshot() === before, 'Menu navigation changed artwork');
    return { nudge: true, layerOrder: true, keyboardUndoRedo: true, focusIsolation: true };
  });
  await step('pointer-layer-reorder-and-history', async () => {
    await select('Matrix target B');
    await page.locator('#layerSearch').fill('');
    await page.locator('#dockSplitter').focus();
    for (let index = 0; index < 4; index++) await page.keyboard.press('ArrowDown');
    await page.evaluate(async () => {
      layerScrollPane().scrollTop = 0; renderVirtualLayerWindow(true);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    const before = await snapshot();
    // The row owns pointer handling. Read current rendered rows atomically,
    // rather than asking CDP for a nested label's separate box model.
    const geometry = await page.evaluate(() => {
      const ids = ['matrix-target-1', 'matrix-target-0'];
      const objects = ids.map(id => vinylObjects().find(object => object.kloudy.editor_id === id));
      if (objects.some(object => !object)) throw Error('Reorder fixture targets are missing');
      const keys = objects.map(layerListObjectKey);
      const rows = keys.map(key => document.querySelector(`#layers .layerRow[data-layer-list-key="${key}"]`));
      if (rows.some(row => !row?.isConnected)) throw Error('Reorder target rows are not currently mounted');
      const viewport = layerScrollPane().getBoundingClientRect();
      const bounds = rows.map(row => row.getBoundingClientRect());
      if (bounds.some(rect => !rect.width || !rect.height || rect.top < viewport.top || rect.bottom > viewport.bottom)) {
        throw Error('Reorder target rows are clipped or empty');
      }
      const from = { x: bounds[0].left + bounds[0].width / 2, y: bounds[0].top + bounds[0].height / 2 };
      const to = { x: bounds[1].left + bounds[1].width / 2, y: bounds[1].bottom - 6 };
      const hits = [from, to].map(point => document.elementFromPoint(point.x, point.y));
      if (hits.some((hit, index) => !hit || hit.closest('.layerRow') !== rows[index] || isLayerControlTarget(hit))) {
        throw Error('Reorder points do not hit the intended rows outside their controls');
      }
      const selected = selectedVinylObjects();
      if (selected.length !== 1 || selected[0] !== objects[0]) throw Error('Reorder source was not selected through its real row');
      return { from, to, keys, ids, bounds: bounds.map(rect => rect.toJSON()), viewport: viewport.toJSON(),
        hits: hits.map(hit => ({ tag: hit.tagName, className: hit.className })) };
    });
    save('layer-drag-geometry.json', geometry);
    const { from, to } = geometry;
    await page.mouse.move(from.x, from.y); await page.mouse.down();
    try {
      await page.mouse.move(to.x, to.y, { steps: 2 });
      const drag = await page.evaluate(({ from, to }) => ({ from, to, active: layerDragState?.active,
        key: layerDragState?.key, ids: layerDragState?.objects.map(object => object.kloudy.editor_id),
        drop: layerDragState?.dropSlot, hit: document.elementFromPoint(to.x, to.y)?.outerHTML }), { from, to });
      save('layer-drag-target.json', drag);
      check(drag.active && drag.key === geometry.keys[0] && JSON.stringify(drag.ids) === JSON.stringify([geometry.ids[0]])
        && Number.isInteger(drag.drop?.index) && !drag.drop?.groupId, 'Pointer drag did not establish the intended source/reorder slot');
    } finally { await page.mouse.up(); }
    await idle(); const after = await snapshot(); check(before !== after, 'Pointer row reorder did not change stack');
    const expectedOrder = JSON.parse(before).map(shape => shape.editor_id).filter(id => id !== geometry.ids[0]);
    expectedOrder.splice(expectedOrder.indexOf(geometry.ids[1]), 0, geometry.ids[0]);
    check(JSON.stringify(JSON.parse(after).map(shape => shape.editor_id)) === JSON.stringify(expectedOrder), 'Pointer reorder did not move only target B below target A');
    const byId = text => JSON.stringify(JSON.parse(text).sort((a, b) => a.editor_id.localeCompare(b.editor_id)));
    check(byId(before) === byId(after), 'Reorder altered geometry/color/identity');
    check(await page.evaluate(() => layerDragState === null), 'Layer drag state did not clear');
    await historyCycle(before, after);
    await page.locator('#dockSplitter').focus(); await page.keyboard.press('Home');
    return { exactUndoRedo: true, artworkUnchanged: true };
  });
  await step('group-and-ungroup-real-controls', async () => {
    await page.locator('#layerSearch').fill('Matrix target');
    await page.locator('.layerRow').filter({ hasText: 'Matrix target A' }).locator('.layerMain b').click();
    await page.locator('.layerRow').filter({ hasText: 'Matrix target B' }).locator('.layerMain b').click({ modifiers: ['Control'] });
    const before = await snapshot(); await page.locator('#groupSelected').click(); await idle();
    const grouped = await snapshot();
    check(await page.evaluate(() => { const selected = selectedVinylObjects(); return selected.length === 2 && selected[0].kloudy.group_id && selected[0].kloudy.group_id === selected[1].kloudy.group_id; }), 'Group control did not create shared membership');
    await historyCycle(before, grouped);
    await page.locator('#redoBtn').click(); await idle();
    await page.locator('#groupActions').click(); await page.locator('#ungroupSelected').click(); await idle();
    check(await page.evaluate(() => selectedVinylObjects().every(object => !object.kloudy.group_id)), 'Ungroup control retained membership');
    await h.undo(page, grouped); await h.undo(page, before);
    return { grouped: 2, exactUndoRedo: true, ungrouped: true };
  });
  await step('reference-file-controls-and-shortcut', async () => {
    const before = await snapshot();
    const png = await page.evaluate(() => { const element = document.createElement('canvas'); element.width = 512; element.height = 256;
      const context = element.getContext('2d'); context.fillStyle = '#368ea0'; context.fillRect(0, 0, 512, 256);
      context.fillStyle = '#f394ba'; context.fillRect(200, 80, 100, 100); return element.toDataURL().split(',')[1]; });
    const reference = path.join(output, 'matrix-reference.png'); fs.writeFileSync(reference, Buffer.from(png, 'base64'));
    await page.locator('[data-tool-mode="overlay"]').click(); await h.fileInput(page, '#overlayInput', reference);
    await page.waitForFunction(() => !!editorReference.image);
    await page.locator('#overlayScalePercent').fill('120'); await page.locator('#overlayScalePercent').press('Enter');
    await page.locator('#overlayOpacity').fill('60');
    await page.locator('#overlayLayerMode').selectOption('above');
    await page.locator('#overlaySizeLock').click();
    check(await page.locator('#overlayScalePercent').isDisabled(), 'Reference size lock did not disable editing');
    const original = await page.evaluate(() => editorReference.sourceOverlayProjectState());
    check(original.controls.scale_percent === 120 && original.controls.opacity_percent === 60 && original.controls.size_locked
      && original.controls.layer_mode === 'above' && Math.abs(original.transform.opacity - .6) < 1e-8, 'Reference controls did not apply their requested state');
    await shortcutFocus(); await page.keyboard.press('Space');
    check(await page.evaluate(() => editorReference.image.visible === false), 'Reference hide shortcut failed');
    await page.keyboard.press('Space');
    check(await page.evaluate(() => editorReference.image.visible === true), 'Reference restore shortcut failed');
    check(JSON.stringify(await page.evaluate(() => editorReference.sourceOverlayProjectState())) === JSON.stringify(original), 'Reference toggle changed reference state');
    await page.locator('#overlayLayerMode').selectOption('below');
    check(await snapshot() === before, 'Reference operations changed artwork');
    return { actualPngInput: true, sizePercent: 120, opacity: 60, locked: true, layerModes: ['above', 'below'], shortcut: true };
  });
  }
  await step('save-disk-readback-new-reopen', async () => {
    const expected = await snapshot(), reference = await page.evaluate(() => editorReference.sourceOverlayProjectState());
    const expectedCount = JSON.parse(expected).length;
    if (!options.saveOnly) check(expectedCount === config.count, 'Matrix changed the final layer count');
    const projectName = `Host matrix ${name}`;
    await command('saveProjectAs'); await page.locator('#textPromptInput').fill(projectName); await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    const processInfo = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
    const projectDir = path.join(processInfo.profile, 'projects');
    const diskProjects = fs.readdirSync(projectDir).filter(file => file.endsWith('.json')).map(file => ({ file, value: JSON.parse(fs.readFileSync(path.join(projectDir, file), 'utf8')) }));
    const saved = diskProjects.find(item => JSON.stringify(item.value.shapes) === expected);
    check(saved && saved.value.layer_count === expectedCount, 'Actual saved project file does not match scene');
    await command('newCanvas'); await page.waitForFunction(() => vinylObjects().length === 0);
    await page.locator('#loadProject').click();
    await page.locator('.projectBrowserEntry').filter({ has: page.getByText(projectName, { exact: true }) }).click();
    await page.locator('#selectProjectEntry').click();
    await page.waitForFunction(count => vinylObjects().length === count && !recoveryRestoreDepth && !documentDirty, expectedCount);
    check(await snapshot() === expected, 'Reopened shapes/order/group metadata differ');
    check(JSON.stringify(await page.evaluate(() => editorReference.sourceOverlayProjectState())) === JSON.stringify(reference), 'Reopened reference state differs');
    save('project-readback.json', { file: saved.file, layers: expectedCount, exactShapes: true, exactReference: true });
    return { diskFile: saved.file, layers: expectedCount, exactShapes: true, exactReference: true, savedAndIdle: true };
  });
  await page.locator('#layerSearch').fill(''); await page.locator('#workspaceFit').click();
  report.finalScene = await h.scene(page);
  report.redrawMs = await page.evaluate(() => Array.from({ length: 3 }, () => { const start = performance.now(); canvas.renderAll(); return performance.now() - start; }));
  report.passed = true; save('host-editing-matrix.json', report);
  await page.mouse.move(1, 1);
  await page.screenshot({ path: path.join(output, 'host-editing-matrix.png') });
  return report;
}
