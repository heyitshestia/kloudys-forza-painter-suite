async (page, options = {}) => {
  page.setDefaultTimeout(30000);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const reloadReference = async () => {
    if (options.hostRestart) return; // The Chrome harness verifies a real host restart instead of raw browser reload.
    await page.reload();
    await page.waitForFunction(() => window.KfpsDesktop?.ready && (editorReference.image || $('autosaveRecoveryDialog').open));
    if (await page.locator('#autosaveRecoveryDialog').isVisible()) {
      await page.locator('#recoverAutosave').click();
      await page.waitForFunction(() => !!editorReference.image && !recoveryRestoreDepth);
      await page.locator('#saveProject').click();
      await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    }
  };
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 1400 }, (_, i) => ({
      type: 1048677 + i % 3, data: [i % 40 * 30 - 600, Math.floor(i / 40) * 30 - 500, .2, .2, 0, 0, 0], color: [70, 150, 220, 255],
    })) });
    window.__lockShapes = JSON.stringify(snapshotShapes());
  });
  await page.locator('[data-panel="overlayPane"]').click();
  check(await page.locator('#overlaySizeLock').isDisabled(), 'Empty reference can be locked');
  const png = await page.evaluate(() => {
    const fixture = document.createElement('canvas'); fixture.width = 512; fixture.height = 256;
    const c = fixture.getContext('2d'); c.fillStyle = '#368ea0'; c.fillRect(0, 0, 512, 256);
    c.fillStyle = '#f394ba'; c.fillRect(200, 80, 100, 100); return fixture.toDataURL().split(',')[1];
  });
  await page.locator('#overlayInput').setInputFiles({ name: 'lock-reference.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await page.waitForFunction(() => !!editorReference.image);
  await page.locator('#overlayScalePercent').fill('120');
  await page.locator('#overlayScalePercent').press('Enter');
  const original = await page.evaluate(() => editorReference.sourceOverlayProjectState());
  await page.locator('#overlaySizeLock').click();
  check(await page.locator('#overlayScale').isDisabled() && await page.locator('#overlayScalePercent').isDisabled(), 'Size controls remain active');
  const unchanged = () => page.evaluate(original => {
    const transform = editorReference.sourceOverlayProjectState().transform;
    return transform.scaleX === original.transform.scaleX && transform.scaleY === original.transform.scaleY
      && JSON.stringify(snapshotShapes()) === __lockShapes;
  }, original);
  const slider = await page.locator('#overlayScale').boundingBox();
  await page.mouse.click(slider.x + slider.width * .95, slider.y + slider.height / 2);
  await page.keyboard.press('ArrowRight');
  await page.evaluate(() => {
    for (const [id, event] of [['overlayScale', 'input'], ['overlayScalePercent', 'change']]) {
      $(id).value = '350'; $(id).dispatchEvent(new Event(event, { bubbles: true }));
    }
  });
  check(await unchanged() && await page.locator('#overlayScalePercent').inputValue() === '120', 'Locked input changed reference/artwork');
  for (const key of ['Home', 'End', 'Home']) {
    await page.locator('#overlayOpacity').focus(); await page.locator('#overlayOpacity').press(key);
    check(await page.evaluate(key => editorReference.image.opacity === (key === 'End' ? 1 : 0), key), 'Opacity blocked');
    check(await unchanged(), 'Opacity resized reference');
  }
  await page.locator('#overlayOpacity').press('ArrowRight');
  await page.locator('#overlayLayerMode').selectOption('above');
  await page.locator('[data-tool-mode="source"]').click();
  const box = await page.locator('.upper-canvas').boundingBox();
  const start = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  const beforeMove = await page.evaluate(() => editorReference.image.left);
  await page.mouse.move(start.x, start.y); await page.mouse.down();
  await page.mouse.move(start.x + 35, start.y + 20, { steps: 8 }); await page.mouse.up();
  check(await page.evaluate(before => editorReference.image.left !== before, beforeMove), 'Lock prevented reference movement');
  check(await unchanged(), 'Reference drag changed size/artwork');
  await page.locator('[data-panel="overlayPane"]').click();
  await page.locator('#overlaySizeLock').focus(); await page.locator('#overlaySizeLock').press('Space');
  check(!await page.locator('#overlayScalePercent').isDisabled(), 'Keyboard unlock failed');
  await page.locator('#overlayScalePercent').fill('160'); await page.locator('#overlayScalePercent').press('Enter');
  check(await page.evaluate(() => editorReference.sourceOverlayProjectState().controls.scale_percent === 160), 'Unlocked resizing failed');
  await page.locator('#overlaySizeLock').click();
  const saved = await page.evaluate(() => editorReference.sourceOverlayProjectState());
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Reference size lock regression'); await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => { await flushPendingAutosave(); });
  check(await page.evaluate(saved => JSON.stringify(saved) === JSON.stringify(editorReference.sourceOverlayProjectState()), saved), 'Save changed reference');
  await reloadReference();
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({ hasText: 'Reference size lock regression' }).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(() => !$('projectBrowserDialog').open && !documentDirty);
  await page.locator('[data-panel="overlayPane"]').click();
  check(await page.locator('#overlayScale').isDisabled(), 'Project/restart lost lock');
  check(await page.evaluate(saved => JSON.stringify(saved) === JSON.stringify(editorReference.sourceOverlayProjectState()), saved), 'Project restore changed reference');
  await page.locator('#overlaySizeLock').click();
  check(await page.evaluate(() => documentDirty), 'Lock change not saved as an edit');
  await page.evaluate(async () => { await flushPendingAutosave(); });
  check(await page.evaluate(async () => (await readAutosavePayload()).editor_source_overlay.controls.size_locked === false), 'Recovery lost changed lock');
  await page.locator('#overlaySizeLock').click();
  await page.evaluate(async () => { await flushPendingAutosave(); });
  check(await page.evaluate(async () => (await readAutosavePayload()).editor_source_overlay.controls.size_locked === true), 'Recovery lost enabled lock');
  const layouts = [];
  for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) {
    await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
    for (const width of [1760, 1280, 900]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.locator('[data-panel="overlayPane"]').click();
      const fits = await page.evaluate(() => {
        const row = $('overlaySizeLock').parentElement, r = row.getBoundingClientRect();
        const children = [...row.children].map(e => e.getBoundingClientRect());
        return children.every((c, i) => c.width > 0 && c.left >= r.left - 1 && c.right <= r.right + 1
          && (!i || c.left >= children[i - 1].right - 1));
      });
      check(fits, `Reference control overlaps in ${theme}/${width}`);
      layouts.push({ theme, width, fits });
      if (width === 1280) await page.locator('#overlayPane').screenshot({ path: path.join(output, `reference-lock-${theme}.png`) });
    }
  }
  await page.locator('#removeOverlay').click();
  check(await page.locator('#overlaySizeLock').isDisabled() && !await page.locator('#overlayScale').isDisabled(), 'Removal left stale lock');
  await page.evaluate(async saved => {
    const old = structuredClone(saved); delete old.controls.size_locked;
    await editorReference.restoreSourceOverlayFromProject(old);
  }, saved);
  check(!await page.locator('#overlayScale').isDisabled(), 'Old project incorrectly locked');
  await page.locator('#saveProject').click(); await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  if (!options.hostRestart) {
    await page.evaluate(async () => {
      KfpsEditorPreferences.setItem(KfpsI18n.KEY, 'ko');
      await KfpsEditorPreferences.flush(); await flushPendingAutosave();
    });
    await reloadReference();
    await page.locator('[data-panel="overlayPane"]').click();
    check(await page.locator('#overlaySizeLock').getAttribute('title') === '\ucc38\uc870 \uc774\ubbf8\uc9c0 \ud06c\uae30 \uc7a0\uae08', 'Korean lock tooltip missing');
  }
  await page.locator('#overlaySizeLock').click();
  if (!options.hostRestart) {
    check(await page.locator('#overlaySizeLock').getAttribute('title') === '\ucc38\uc870 \uc774\ubbf8\uc9c0 \ud06c\uae30 \uc7a0\uae08 \ud574\uc81c', 'Korean unlock tooltip missing');
    await page.locator('#overlayPane').screenshot({ path: path.join(output, 'reference-lock-korean.png') });
  }
  await page.locator('#saveProject').click(); await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  return { layers: 1400, trustedControls: true, staleEvents: true, opacity: true, movement: true,
    keyboardUnlock: true, savedProjectReopen: true, recovery: true, oldProjects: true, removal: true, korean: !options.hostRestart, layouts };
}
