async (page, options = {}) => {
  page.setDefaultTimeout(20000);
  const check = (ok, message) => { if (!ok) throw Error(message); };
  if (options.workflowRestart) {
    check(await page.evaluate(() => KfpsI18n.language === 'ko' && shortcutFor('colorSlot16') === 'Ctrl+Shift+9'
      && JSON.stringify(favoriteColors[15]) === JSON.stringify([49, 70, 150, 255])), 'Restart lost language, shortcut or palette');
    await page.locator('#loadProject').click();
    await page.locator('#projectBrowserEntries button').filter({ hasText: 'Workflow layout regression' }).dblclick();
    await page.waitForFunction(() => !editorCommands.busy && vinylObjects().length === 3);
    check(await page.evaluate(() => membersForGroupIds(['layout-group']).length === 2
      && !locatedLayerListKey && !document.querySelector('#layers .layerLocated')), 'Restart lost grouping or restored transient highlight');
    return { freshHostRestart: true, language: 'ko', shortcut: true, palette: true, savedGrouping: true };
  }
  const layouts = [];
  for (const language of ['en', 'ko']) {
    await page.evaluate(async language => {
      KfpsEditorPreferences.setItem(KfpsI18n.KEY, language);
      await KfpsEditorPreferences.flush(); await flushPendingAutosave();
    }, language);
    await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready);
    await page.evaluate(async () => {
      document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
      await loadPayload({ shapes: Array.from({ length: 3 }, (_, i) => ({
        type: 1048677, color: [100, 160, 200, 255], data: [i * 150, 0, .5, .5, 0, 0, 0], editor_id: `layout-${i}`,
        ...(i < 2 ? { editor_group_id: 'layout-group', editor_group_name: 'Group <test> & "quotes"' } : {})
      })) });
      selectObjects([vinylObjects()[2]], 'test');
      setDockVisible(true); setLayersCollapsed(false);
      favoriteColors[15] = [49, 70, 150, 255]; saveFavoriteColors();
      setShortcut('colorSlot16', 'Ctrl+Shift+9');
    });
    check(await page.evaluate(language => KfpsI18n.language === language, language), 'Language did not apply');
    for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) {
      await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
      for (const size of [{ width: 1760, height: 1040 }, { width: 1280, height: 800 }, { width: 900, height: 640 }]) {
        await page.setViewportSize(size);
        await page.locator('#groupActions').click();
        const menu = await page.locator('#layerGroupActions').boundingBox();
        check(menu && menu.x >= 0 && menu.y >= 0 && menu.x + menu.width <= size.width && menu.y + menu.height <= size.height,
          `Group menu outside viewport: ${language}/${theme}/${size.width}`);
        await page.locator('#addSelectedToGroup').click();
        check(await page.locator('#addToGroupTarget option').innerText() === 'Group <test> & "quotes"', 'Group label was not preserved as plain text');
        const dialogFits = await page.locator('#addToGroupDialog').evaluate(dialog => {
          const rect = dialog.getBoundingClientRect();
          return rect.x >= 0 && rect.y >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight
            && dialog.scrollWidth <= dialog.clientWidth + 2
            && dialog.querySelector('h2').getBoundingClientRect().left >= rect.left + 12
            && dialog.querySelector('label').getBoundingClientRect().left >= rect.left + 12;
        });
        check(dialogFits, `Group dialog clipped: ${language}/${theme}/${size.width}`);
        if (size.width === 1280) await page.screenshot({ path: path.join(output, `group-dialog-${language}-${theme}.png`) });
        await page.locator('#cancelAddToGroup').click();
        await page.evaluate(() => openColorDialog());
        check(await page.locator('#favoriteColorGrid').evaluate(grid => grid.scrollWidth <= grid.clientWidth
          && [...grid.children].every(button => button.scrollWidth <= button.clientWidth + 2 && button.scrollHeight <= button.clientHeight + 2)),
        `Palette clipped: ${language}/${theme}/${size.width}`);
        await page.locator('#closeColorDialog').click();
        layouts.push({ language, theme, ...size, menu: true, dialog: true, palette: true });
      }
    }
    if (language === 'ko') {
      await page.locator('#shortcutsBtn').click();
      check(await page.locator('[data-shortcut-action="toggleReference"]').locator('..').innerText() !== 'Show / hide reference image', 'Korean reference shortcut label missing');
      await page.keyboard.press('Escape');
    }
    await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill(language === 'ko' ? 'Workflow layout regression' : 'Workflow layout English');
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  }
  await page.evaluate(async () => { await KfpsEditorPreferences.flush(); await flushPendingAutosave(); });
  return { layouts, groupNamesEscaped: true, koreanShortcuts: true, restartFixtureSaved: true };
}
