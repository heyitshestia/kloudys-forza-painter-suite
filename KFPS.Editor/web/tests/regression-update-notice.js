async (page, options = {}) => {
  const check = (value, message) => { if (!value) throw Error(message); };
  const phase = options.noticePhase || "confirm";
  const previous = options.previousOutput;
  const ready = () => page.waitForFunction(() => window.KfpsDesktop?.ready);
  const confirm = async () => {
    await page.locator('#editorUpdateAcknowledge').check();
    await page.locator('#editorUpdateContinue').click();
    await page.locator('#editorUpdateDialog').waitFor({ state: 'hidden' });
  };
  await ready();
  if (phase === 'unconfirmed') {
    for (const [dialog, checkbox, button] of [
      ['startupHelpDialog', 'startupHelpDontShow', 'startupHelpConfirm'],
      ['projectSharingDialog', 'projectSharingAcknowledge', 'projectSharingContinue'],
      ['languageNoticeDialog', 'languageNoticeAcknowledge', 'languageNoticeContinue'],
    ]) {
      await page.locator(`#${dialog}`).waitFor({ state: 'visible' });
      check(await page.locator('#editorUpdateDialog').isHidden(), 'Update notice overlaps an earlier notice');
      await page.locator(`#${checkbox}`).check();
      await page.locator(`#${button}`).click();
    }
    await page.locator('#editorUpdateDialog').waitFor({ state: 'visible' });
    await page.locator('#editorUpdateAcknowledge').check();
    check(await page.evaluate(() => editorSettings.getItem(EDITOR_UPDATE_ACK_KEY)) === null,
      'Checking alone acknowledged the notice');
    return { startupOrder: true, checkedWithoutOK: true };
  }
  if (phase === 'restart' || phase === 'pending-recovery') {
    const expected = fs.readFileSync(path.join(previous, 'notice-recovery.json'), 'utf8');
    if (phase === 'pending-recovery') {
      await page.locator('#editorUpdateDialog').waitFor({ state: 'visible' });
      check(await page.evaluate(() => vinylObjects().length) === 0, 'Recovery ran before notice acknowledgement');
      await confirm();
    }
    await page.waitForFunction(() => vinylObjects().length === 2401);
    check(await page.locator('#editorUpdateDialog').isHidden(), 'Acknowledged notice returned after process restart');
    check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === expected, 'Notice/restart changed recovered artwork');
    check(await page.evaluate(() => documentDirty), 'Recovery lost unsaved status');
    if (phase === 'restart') {
      // Simulate the first installation of this notice over an existing recovery.
      await page.evaluate(async () => { editorSettings.removeItem(EDITOR_UPDATE_ACK_KEY); await KfpsEditorPreferences.flush(); });
    } else {
      await page.locator('#saveProject').click();
      await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    }
    return { phase, recoveredExactly: true, layers: 2401, dirtyPreserved: true };
  }
  await page.locator('#editorUpdateDialog').waitFor({ state: 'visible' });
  check(!await page.locator('#editorUpdateAcknowledge').isChecked(), 'Unconfirmed native close retained a checked checkbox');
  const layouts = [];
  for (const language of ['en', 'ko']) {
    await page.evaluate(async language => {
      editorSettings.setItem(KfpsI18n.KEY, language);
      editorSettings.removeItem(EDITOR_UPDATE_ACK_KEY);
      await KfpsEditorPreferences.flush();
    }, language);
    await page.reload(); await ready();
    await page.locator('#editorUpdateDialog').waitFor({ state: 'visible' });
    check(await page.locator('#editorUpdateContinue').isDisabled(), 'Unchecked OK is enabled');
    await page.keyboard.press('Escape');
    await page.locator('#editorUpdateAcknowledge').focus();
    await page.keyboard.press('Enter');
    check(await page.locator('#editorUpdateDialog').isVisible(), 'Keyboard dismissed unacknowledged notice');
    check(await page.evaluate(() => editorSettings.getItem(EDITOR_UPDATE_ACK_KEY)) === null, 'Viewing acknowledged notice');
    check(await page.locator('#editorUpdateTitle').innerText() === (language === 'en'
      ? 'A little editor update from Kloudy' : 'Kloudy가 전하는 에디터 업데이트 소식'), 'Wrong title language');
    check(await page.locator('#editorUpdateContinue').innerText() === (language === 'en' ? 'OK' : '확인'), 'Wrong OK language');
    const link = page.locator('.editorUpdateSupport a');
    check(await link.getAttribute('href') === 'https://ko-fi.com/O7O020EQNQ', 'Wrong support destination');
    check(await link.getAttribute('target') === null, 'Native host cannot open new-window links');
    for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) {
      await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
      for (const size of [{ width: 1440, height: 900 }, { width: 800, height: 600 }, { width: 390, height: 640 }]) {
        await page.setViewportSize(size);
        const layout = await page.evaluate(() => {
          const dialog = document.getElementById('editorUpdateDialog'), body = document.getElementById('editorUpdateMessage');
          const box = dialog.getBoundingClientRect(), button = document.getElementById('editorUpdateContinue').getBoundingClientRect();
          const header = dialog.querySelector('.helpHeader').getBoundingClientRect(), text = body.getBoundingClientRect();
          return { fits: box.x >= 0 && box.y >= 0 && box.right <= innerWidth && box.bottom <= innerHeight,
            footerVisible: button.bottom <= box.bottom && button.top >= text.bottom - 1,
            noOverlap: header.bottom <= text.top + 1,
            noTextOverflow: body.scrollWidth <= body.clientWidth + 1,
            bodyHeight: text.height };
        });
        check(layout.fits && layout.footerVisible && layout.noOverlap && layout.noTextOverflow && layout.bodyHeight > 100,
          `Notice layout ${language}/${theme}/${size.width}: ${JSON.stringify(layout)}`);
        layouts.push({ language, theme, ...size, ...layout });
        await page.screenshot({ path: path.join(output, `${language}-${theme}-${size.width}-notice.png`) });
      }
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.locator('#editorUpdateAcknowledge').check();
    await page.locator('#editorUpdateAcknowledge').uncheck();
    check(await page.locator('#editorUpdateContinue').isDisabled(), 'Unchecking did not disable OK');
    await page.route('**/api/fabric-editor/preferences', route => route.request().method() === 'POST'
      ? route.fulfill({ status: 503, contentType: 'application/json', body: '{"ok":false,"error":"test: disk unavailable"}' })
      : route.continue());
    await page.locator('#editorUpdateAcknowledge').check();
    await page.locator('#editorUpdateContinue').click();
    await page.locator('#editorUpdateError').waitFor({ state: 'visible' });
    check(await page.evaluate(() => editorSettings.getItem(EDITOR_UPDATE_ACK_KEY)) === null, 'Failed write retained acknowledgement');
    check(await page.locator('#editorUpdateError').innerText() === await page.evaluate(() => KfpsI18n.t('Your acknowledgment could not be saved. Please try again.')), 'Error not localized');
    await page.unroute('**/api/fabric-editor/preferences');
    await confirm();
    check(await page.evaluate(async () => (await (await fetch(EDITOR_PREFS_API)).json()).settings[EDITOR_UPDATE_ACK_KEY]) === 'modernization-1', 'Real preference store did not save acknowledgement');
    await page.reload(); await ready();
    check(await page.locator('#editorUpdateDialog').isHidden(), 'Acknowledged notice returned on reload');
  }
  // A language change must not turn a one-time notice into another prompt.
  await page.evaluate(async () => { editorSettings.setItem(KfpsI18n.KEY, 'en'); await KfpsEditorPreferences.flush(); });
  await page.reload(); await ready();
  check(await page.locator('#editorUpdateDialog').isHidden(), 'Language switch reset acknowledgement');
  await page.evaluate(async () => {
    const shapes = Array.from({ length: 2400 }, (_, i) => ({ type: 1048677, color: [40, 180, 150, 200],
      data: [(i % 60) * 20 - 600, Math.floor(i / 60) * 20 - 400, .12, .12, i % 90, 0, 0], shape_name: `Notice fixture ${i}` }));
    await loadPayload({ shapes });
  });
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Notice recovery integration');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(() => { canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel(); });
  await page.locator('#duplicateLayer').click();
  await page.waitForFunction(() => vinylObjects().length === 2401 && documentDirty);
  const expected = await page.evaluate(async () => {
    await flushPendingAutosave();
    const saved = await readAutosavePayload();
    if (JSON.stringify(saved.shapes) !== JSON.stringify(snapshotShapes())) throw Error('Recovery did not save exact notice fixture');
    return JSON.stringify(snapshotShapes());
  });
  fs.writeFileSync(path.join(output, 'notice-recovery.json'), expected);
  return { requiredConfirmation: true, failureRetry: true, reloadAndLanguageSafe: true, layouts,
    recoveryLayers: 2401, saveAsEnter: true, supportPolicy: 'ordinary external link; native unit test intercepts OS launch' };
}
