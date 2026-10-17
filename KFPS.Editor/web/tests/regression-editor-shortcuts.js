async (page) => {
  page.setDefaultTimeout(20000);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  await page.evaluate(async () => {
    resetShortcuts();
    await loadPayload({ shapes: [{ type: 1048677, data: [0, 0, 1, 1, 0, 0, 0], color: [10, 20, 30, 255], editor_id: 'shortcut-test' }] });
    selectObjects(vinylObjects(), 'test');
    favoriteColors = Array.from({ length: 16 }, (_, i) => [20 + i * 12, 100, 220 - i * 10, 255]); saveFavoriteColors();
    activateDockPanel('overlayPane');
  });
  const png = await page.evaluate(() => { const c = document.createElement('canvas'); c.width = c.height = 32; return c.toDataURL().split(',')[1]; });
  await page.locator('#overlayInput').setInputFiles({ name: 'shortcut-reference.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await page.waitForFunction(() => !!editorReference.image);
  await page.locator('#shortcutsBtn').click();
  const field = page.locator('[data-shortcut-action="colorSlot1"]');
  const rejected = [
    { key: 'ArrowLeft' }, { key: 'ArrowRight', ctrlKey: true }, { key: 'Home' }, { key: 'Enter' },
    { key: 'Backspace' }, { key: 'Delete', shiftKey: true }, { key: ' ', altKey: true },
    { key: 'F4', altKey: true }, { key: 'r', metaKey: true }, { key: 'F5' }, { key: 'F12' },
    { key: 'r', ctrlKey: true }, { key: 'w', ctrlKey: true }, { key: 't', ctrlKey: true },
    { key: '+', ctrlKey: true }, { key: 'i', ctrlKey: true, shiftKey: true }, { key: 'c', ctrlKey: true },
  ];
  // Dispatch dangerous/reserved keys to the actual capture handler only. Never
  // send window-close/system accelerators to the user's operating system.
  for (const event of rejected) {
    await field.focus(); await field.dispatchEvent('keydown', { ...event, bubbles: true, cancelable: true });
    check(await field.inputValue() === '1', `Protected binding was accepted: ${JSON.stringify(event)}`);
    check((await page.locator('#shortcutEditorStatus').innerText()).length > 10, 'Rejection is invisible inside the dialog');
  }
  await field.focus(); await page.keyboard.press('Tab');
  check(await field.evaluate(el => document.activeElement !== el), 'Shortcut input traps Tab navigation');
  await field.focus(); await page.keyboard.press('Escape');
  check(await field.inputValue() === '1', 'Escape changed binding');
  // Assign every new action via the real Keys UI and execute all 16 colours.
  for (let i = 0; i < 16; i++) {
    await page.locator(`[data-shortcut-action="colorSlot${i + 1}"]`).click();
    await page.keyboard.press(`Control+${i < 8 ? '' : 'Alt+'}Shift+${i % 8 + 1}`);
  }
  await page.locator('[data-shortcut-action="toggleReference"]').click(); await page.keyboard.press('F8');
  await page.locator('#closeShortcuts').click();
  await page.evaluate(() => document.activeElement?.blur());
  for (let i = 0; i < 16; i++) {
    await page.keyboard.press(`Control+${i < 8 ? '' : 'Alt+'}Shift+${i % 8 + 1}`);
    check(await page.evaluate(i => JSON.stringify(objectToShape(vinylObjects()[0]).color) === JSON.stringify(favoriteColors[i]), i), `Rebound colour ${i + 1} failed`);
  }
  await page.keyboard.press('F8'); check(await page.evaluate(() => !editorReference.image.visible), 'Rebound reference toggle failed');
  await page.keyboard.press('F8'); check(await page.evaluate(() => editorReference.image.visible), 'Rebound reference toggle failed on reuse');
  const before = await page.evaluate(() => JSON.stringify(snapshotShapes()));
  await page.evaluate(() => {
    const event = new KeyboardEvent('keydown', { key: '1', ctrlKey: true, altKey: true, shiftKey: true, bubbles: true, cancelable: true });
    Object.defineProperty(event, 'getModifierState', { value: key => key === 'AltGraph' });
    document.dispatchEvent(event);
  });
  check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === before, 'AltGr input invoked a colour action');
  await page.locator('#saveProjectAs').click(); await page.locator('#textPromptInput').fill('Shortcut validation');
  await page.locator('#textPromptInput').press('Enter'); await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => { await flushPendingAutosave(); await KfpsEditorPreferences.flush(); });
  await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()));
  check(await page.evaluate(() => shortcutFor('toggleReference') === 'F8' && shortcutFor('colorSlot16') === 'Ctrl+Shift+Alt+8'), 'Safe bindings did not survive reload');
  await page.evaluate(async () => {
    editorSettings.setItem(SHORTCUTS_KEY, JSON.stringify({ duplicate: '1', colorSlot2: 'F5', colorSlot3: 'Meta+R',
      colorSlot4: 'F8', colorSlot5: 'F8', colorSlot6: '', toggleReference: 'ArrowLeft' }));
    KfpsEditorPreferences.setItem(KfpsI18n.KEY, 'ko'); await KfpsEditorPreferences.flush(); await flushPendingAutosave();
  });
  await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()));
  await page.locator('#shortcutsBtn').click();
  check(await page.evaluate(() => shortcutFor('duplicate') === '1' && shortcutFor('colorSlot1') === ''
    && shortcutFor('colorSlot2') === '2' && shortcutFor('colorSlot4') === 'F8' && shortcutFor('colorSlot5') === ''
    && shortcutFor('colorSlot6') === '' && shortcutFor('toggleReference') === 'Space'), 'Saved unsafe/duplicate bindings bypassed validation');
  check((await page.locator('#shortcutEditorStatus').innerText()).includes('단축키'), 'Korean migration warning missing');
  await field.focus(); await field.dispatchEvent('keydown', { key: 'F5', bubbles: true, cancelable: true });
  check((await page.locator('#shortcutEditorStatus').innerText()).includes('브라우저'), 'Korean browser rejection missing');
  const layouts = [];
  for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) {
    await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
    for (const size of [{ width: 1760, height: 1040 }, { width: 1280, height: 800 }, { width: 900, height: 640 }]) {
      await page.setViewportSize(size);
      const last = page.locator('[data-shortcut-action="colorSlot16"]');
      await last.focus(); await last.dispatchEvent('keydown', { key: 'F5', bubbles: true, cancelable: true });
      check(await page.locator('#shortcutEditorStatus').evaluate(status => {
        const r = status.getBoundingClientRect(), dialog = document.querySelector('#shortcutsDialog');
        const d = dialog.getBoundingClientRect();
        return r.top >= d.top && r.bottom <= d.bottom && r.left >= d.left && r.right <= d.right
          && d.left >= 0 && d.right <= innerWidth && d.top >= 0 && d.bottom <= innerHeight
          && dialog.scrollWidth <= dialog.clientWidth + 2;
      }), `Shortcut rejection scrolls out of view or clips: ${theme}/${size.width}`);
      layouts.push({ theme, ...size });
    }
  }
  await page.screenshot({ path: path.join(output, 'shortcut-rejection-ko.png') });
  await page.locator('#resetShortcuts').click();
  check(await page.evaluate(() => JSON.stringify(shortcuts) === JSON.stringify(DEFAULT_SHORTCUTS) && !shortcutLoadWarnings.length), 'Reset did not restore usable defaults');
  await page.locator('#closeShortcuts').click();
  await page.evaluate(async () => {
    KfpsEditorPreferences.setItem(KfpsI18n.KEY, 'en'); await KfpsEditorPreferences.flush(); await flushPendingAutosave();
  });
  await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready);
  await page.evaluate(() => document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()));
  return { reservedKeys: rejected.length, allNewActionsRebound: 17, keyboardFocus: true, altGrProtected: true,
    safeBindingsPersist: true, unsafeSavedBindingsRepaired: true, duplicatesRemoved: true, koreanFeedback: true, layouts, reset: true };
}
