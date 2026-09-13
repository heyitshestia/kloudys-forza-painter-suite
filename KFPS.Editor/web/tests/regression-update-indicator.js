async (page, options = {}) => {
  const check = (value, message) => { if (!value) throw Error(message); };
  const key = 'kloudyFabricUpdateBlinkAcknowledged';
  await page.waitForFunction(() => window.KfpsDesktop?.ready && editorUpdates);
  const nativeStatus = await page.evaluate(async () => (await fetch('/api/fabric-editor/update-status', { headers: EDITOR_MUTATION_HEADERS })).json());
  check(nativeStatus.localVersion === fs.readFileSync(path.join(__dirname, '../../../VERSION'), 'utf8').trim(),
    'Independent native host did not publish its update status');
  let status = { ...nativeStatus, latestVersion: '3.1.990', available: true, checked: true, checking: false };
  await page.route('**/api/fabric-editor/update-status', route => route.fulfill({ json: status }));
  const refresh = () => page.evaluate(() => editorUpdates.check());
  const blinking = () => page.locator('#editorUpdateIndicator').evaluate(el => el.classList.contains('isBlinking'));
  await refresh();
  if (options.indicatorPhase === 'restart') {
    check(!await blinking(), 'Acknowledged version blinked after native restart');
    await page.waitForFunction(() => vinylObjects().length === 2401);
    const expected = fs.readFileSync(path.join(options.previousOutput, 'indicator-recovery.json'), 'utf8');
    check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === expected, 'Native restart changed recovered artwork');
    check(await page.evaluate(() => documentDirty), 'Native restart lost dirty status');
    status.latestVersion = '3.1.991'; await refresh();
    check(await blinking(), 'Later version did not blink after restart');
    await page.locator('#saveProject').click();
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    return { phase: 'restart', durableAcknowledgement: true, laterUpdateBlinks: true, exactRecoveryLayers: 2401, nativeStatus };
  }
  check(await blinking(), 'New update did not blink');
  const layouts = [];
  for (const language of ['en', 'ko']) {
    await page.evaluate(async language => { editorSettings.setItem(KfpsI18n.KEY, language); await editorSettings.flush(); }, language);
    await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready && editorUpdates);
    await refresh();
    check(await page.locator('#editorUpdateIndicator').innerText() === (language === 'ko' ? '업데이트' : 'UPDATE'), 'Indicator language mismatch');
    for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) {
      await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
      for (const width of [1440, 900, 800]) {
        await page.setViewportSize({ width, height: 900 });
        const geometry = await page.evaluate(() => {
          const button = document.getElementById('editorUpdateIndicator'), brand = document.querySelector('.brandBlock');
          const a = button.getBoundingClientRect(), b = brand.getBoundingClientRect();
          const style = getComputedStyle(button);
          return { fits: a.left >= 0 && a.right <= innerWidth && a.top >= 0 && a.bottom <= 68,
            noOverlap: a.right <= b.left, textFits: button.scrollWidth <= button.clientWidth,
            color: style.color, background: style.backgroundColor, animation: style.animationName };
        });
        check(geometry.fits && geometry.noOverlap && geometry.textFits, `Layout failed ${language}/${theme}/${width}: ${JSON.stringify(geometry)}`);
        check(geometry.animation === 'editorUpdatePulse', 'Animation missing');
        layouts.push({ language, theme, width, ...geometry });
      }
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.screenshot({ path: path.join(output, `indicator-${language}.png`) });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    check(await page.locator('#editorUpdateIndicator').evaluate(el => getComputedStyle(el).animationName) === 'none', 'Reduced motion not respected');
    await page.emulateMedia({ reducedMotion: 'no-preference' });
  }
  await page.evaluate(async () => { editorSettings.setItem(KfpsI18n.KEY, 'en'); await editorSettings.flush(); });
  await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready && editorUpdates);
  await refresh();
  await page.evaluate(async () => {
    const shapes = Array.from({ length: 2400 }, (_, i) => ({ type: 1048677, color: [40, 180, 150, 200],
      data: [(i % 60) * 20 - 600, Math.floor(i / 60) * 20 - 400, .12, .12, i % 90, 0, 0], shape_name: `Indicator fixture ${i}` }));
    await loadPayload({ shapes });
  });
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Update indicator integration');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(() => { canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel(); });
  await page.locator('#duplicateLayer').click();
  await page.waitForFunction(() => vinylObjects().length === 2401 && documentDirty);
  const before = await page.evaluate(() => JSON.stringify(snapshotShapes()));
  await page.route('**/api/fabric-editor/preferences', route => route.request().method() === 'POST'
    ? route.fulfill({ status: 503, json: { ok: false, error: 'test: disk unavailable' } }) : route.continue());
  await page.locator('#editorUpdateIndicator').click();
  await page.waitForFunction(() => !document.getElementById('editorUpdateIndicator').disabled);
  check(!await blinking(), 'Failed preference save kept blinking');
  check((await page.locator('#editorUpdateIndicator').getAttribute('title')).includes('could not be saved yet'), 'Missing failed-save explanation');
  check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === before, 'Acknowledgement changed artwork');
  check(await page.evaluate(() => documentDirty), 'Acknowledgement cleared dirty state');
  await page.unroute('**/api/fabric-editor/preferences');
  await page.locator('#editorUpdateIndicator').focus(); await page.keyboard.press('Enter');
  await page.waitForFunction(() => !document.getElementById('editorUpdateIndicator').disabled);
  check(await page.evaluate(async key => (await (await fetch(EDITOR_PREFS_API)).json()).settings[key], key) === '3.1.990', 'Acknowledgement not in real preference store');
  status.latestVersion = '3.1.991'; await refresh(); check(await blinking(), 'Next update did not blink');
  await page.unroute('**/api/fabric-editor/update-status');
  await page.route('**/api/fabric-editor/update-status', route => route.fulfill({ status: 503, json: {} }));
  await refresh(); check(await blinking(), 'Offline check removed known offer');
  await page.unroute('**/api/fabric-editor/update-status');
  status = { ...status, available: false }; await page.route('**/api/fabric-editor/update-status', route => route.fulfill({ json: status }));
  await refresh(); check(await page.locator('#editorUpdateIndicator').isHidden(), 'Current installation retained indicator');
  status = { ...status, available: true, latestVersion: '3.1.990' }; await refresh();
  check(!await blinking(), 'Acknowledged version blinked on refresh');
  const expected = await page.evaluate(async () => {
    await flushPendingAutosave();
    const saved = await readAutosavePayload();
    if (JSON.stringify(saved.shapes) !== JSON.stringify(snapshotShapes())) throw Error('Update indicator altered recovery');
    return JSON.stringify(snapshotShapes());
  });
  check(expected === before, 'Update checks changed the document');
  fs.writeFileSync(path.join(output, 'indicator-recovery.json'), expected);
  return { phase: 'confirm', nativeStatus, layouts, reducedMotion: true, saveFailureRetry: true,
    keyboardAcknowledgement: true, laterUpdateBlinks: true, offlineSafe: true, exactRecoveryLayers: 2401 };
}
