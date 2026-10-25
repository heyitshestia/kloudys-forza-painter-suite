async (page) => {
  page.setDefaultTimeout(15000);
  const evidence = [];
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const settle = async () => {
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.waitForTimeout(80);
  };
  const row = key => page.locator(`[data-layer-list-key="${key}"]`);
  const measure = key => page.evaluate(key => {
    const pane = layerScrollPane(), entry = layerListRows.get(key), node = entry?.element;
    const rect = node?.getBoundingClientRect(), area = pane.getBoundingClientRect();
    return { top: pane.scrollTop, height: pane.clientHeight, total: pane.scrollHeight,
      groupTop: rect?.top ?? null, visible: Boolean(rect && rect.top >= area.top - 1 && rect.bottom <= area.bottom + 1),
      locked: entry?.locks, visibility: entry?.visibility, parentTop: $('layersPane').scrollTop,
      focusedKey: document.activeElement?.closest('[data-layer-list-key]')?.dataset.layerListKey,
      focusedClass: document.activeElement?.className, rows: $('layers').children.length };
  }, key);
  const position = async (key, end = false) => {
    await page.evaluate(({ key, end }) => {
      const pane = layerScrollPane(), entry = layerListRows.get(key);
      pane.scrollTop = end ? pane.scrollHeight : entry.virtualTop - (pane.clientHeight - 56) / 2;
      renderVirtualLayerWindow(true);
    }, { key, end });
    await settle();
  };
  const change = async (key, selector, input, label) => {
    if (input !== 'mouse') await row(key).locator(selector).focus();
    await settle();
    const before = await measure(key);
    check(before.visible, `${label}: fixture target is not fully visible`);
    if (input === 'mouse') await row(key).locator(selector).click();
    else await page.keyboard.press(input);
    await settle();
    const after = await measure(key);
    evidence.push({ label, selector, input, before, after });
    fs.writeFileSync(path.join(output, 'group-lock-scroll.json'), JSON.stringify(evidence, null, 2));
    if (Math.abs(after.top - before.top) > 1 || after.parentTop !== before.parentTop || !after.visible) {
      await page.screenshot({ path: path.join(output, 'group-lock-scroll-failure.png') });
      throw Error(`${label}: scroll changed or group disappeared: ${JSON.stringify(evidence.at(-1))}`);
    }
    check(after.rows < 60, `${label}: virtualization was lost`);
    if (input !== 'mouse') check(after.focusedKey === key && after.focusedClass.includes(selector.slice(1)),
      `${label}: keyboard focus was not retained on the group control`);
    return { before, after };
  };
  for (const count of [300, 3000]) {
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.evaluate(async count => {
      KfpsDocking.reset();
      const shapes = Array.from({ length: count }, (_, index) => {
        const group = Math.floor(index / 10);
        return { type: 1048677, color: [80, 160, 220, 255],
          data: [index % 30 * 20, Math.floor(index / 30) % 30 * 20, .1, .1, 0, 0, 0],
          editor_id: `scroll-shape-${index}`, editor_group_path: [
            { id: `scroll-group-${group}`, name: `Scroll group ${group}` },
            ...(index % 10 < 5 ? [{ id: `scroll-inner-${group}`, name: `Inner ${group}` }] : []),
          ] };
      });
      await loadPayload({ shapes });
      activateDockPanel('layersPane');
      refreshLayers();
    }, count);
    const original = await page.evaluate(() => JSON.stringify(snapshotShapes()));
    for (const width of [1600, 1024]) for (const collapsed of [false, true]) {
      await page.setViewportSize({ width, height: width === 1600 ? 1000 : 768 });
      await page.evaluate(({ count, collapsed }) => {
        collapsedLayerGroups.clear();
        if (collapsed) for (let i = 0; i < count / 10; i++) collapsedLayerGroups.add(`scroll-group-${i}`);
        clearLayerSelection(); refreshLayers();
      }, { count, collapsed });
      for (const target of collapsed ? ['scroll-group-2', 'scroll-group-0'] : ['scroll-group-2', 'scroll-inner-2']) {
        const key = `group:${target}`, label = `${count}/${width}/${collapsed ? 'collapsed' : 'expanded'}/${target}`;
        await position(key, target === 'scroll-group-0');
        for (const input of ['mouse', 'Enter', 'Space']) for (const selector of ['.layerGroupLock', '.layerGroupVisibility']) {
          for (let toggle = 0; toggle < 2; toggle++) {
            const { before, after } = await change(key, selector, input, `${label}/${toggle}`);
            if (selector === '.layerGroupLock') check(Boolean(before.locked.locked) !== Boolean(after.locked.locked), 'Lock state did not change');
            else check(Boolean(before.visibility.visible) !== Boolean(after.visibility.visible), 'Visibility did not change');
          }
        }
      }
    }
    check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === original, 'Paired state toggles changed artwork or group structure');

    // The same original panel must work when floated, not just in its home dock.
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.locator('#layersPane h2').click({ button: 'right' });
    await page.locator('[data-dock-action="float"]').click();
    await settle();
    const key = 'group:scroll-group-2';
    await position(key);
    await change(key, '.layerGroupLock', 'mouse', `${count}/floating/lock`);
    const locked = await page.evaluate(() => JSON.stringify(snapshotShapes()));
    const beforeUndo = await measure(key);
    await page.locator('#undoBtn').click();
    await page.waitForFunction(() => !editorCommands.busy);
    await settle();
    check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === original, 'Group lock undo changed artwork');
    check(Math.abs((await measure(key)).top - beforeUndo.top) <= 1, 'Group lock undo lost scroll position');
    await page.locator('#redoBtn').click();
    await page.waitForFunction(() => !editorCommands.busy);
    await settle();
    check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === locked, 'Group lock redo did not restore exact state');
    check(Math.abs((await measure(key)).top - beforeUndo.top) <= 1, 'Group lock redo lost scroll position');
    await change(key, '.layerGroupLock', 'Enter', `${count}/floating/unlock`);
    check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === original, 'Floating group operations changed artwork');

    await page.locator('#layerSearch').fill('Scroll group 2');
    await settle();
    check((await measure(key)).top === 0, 'Search no longer resets list to the first result');
    await page.locator('#layerSearch').fill('no-such-scroll-group');
    await settle();
    check(await page.locator('#layers [data-layer-list-key]').count() === 0, 'Empty search retained stale virtual rows');
    await page.locator('#layerSearch').fill('');
    await settle();
    await position(key);
    await page.screenshot({ path: path.join(output, `group-lock-scroll-${count}.png`) });
    await page.evaluate(() => KfpsDocking.reset());
  }
  return { passed: true, actions: evidence.length, counts: [300, 3000], widths: [1600, 1024] };
}
