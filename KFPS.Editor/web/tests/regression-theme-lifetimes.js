async page => {
  const results = await page.evaluate(async () => {
    const results = [], realFetch = window.fetch;
    const run = async (name, action) => {
      try { await action(); results.push({ name, passed: true }); }
      catch (error) { results.push({ name, passed: false, error: error.message }); }
      finally { window.fetch = realFetch; document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close()); }
    };
    const check = (value, message) => { if (!value) throw Error(message); };
    await run('saved theme remains selected if a following list refresh fails', async () => {
      editorTheme.applyEditorTheme('blackout');
      editorTheme.openThemeAdjustDialog();
      $('themeAdjustName').value = 'Committed theme';
      const accent = document.querySelector('[data-theme-var="--accent"]');
      accent.value = '#79bca1'; accent.dispatchEvent(new Event('input', { bubbles: true }));
      window.fetch = (url, options) => String(url) === EDITOR_THEMES_API && options?.method !== 'POST'
        ? Promise.resolve(new Response('{}', { status: 503 })) : realFetch(url, options);
      await editorTheme.saveAdjustedTheme();
      check(document.documentElement.dataset.editorTheme === 'custom', 'Committed custom theme fell back to a built-in');
      check(editorTheme.themeFieldCurrentValues()['--accent'] === '#79bca1', 'Saved color was lost');
      check(editorSettings.getItem('kloudyFabricTheme') === $('editorThemeSelect').value, 'Saved theme and preference diverged');
    });
    await run('failed theme refresh preserves the existing custom catalog', async () => {
      await editorTheme.loadEditorThemes();
      const before = [...editorTheme.entries.keys()].join();
      window.fetch = (url, options) => String(url) === EDITOR_THEMES_API
        ? Promise.resolve(new Response('{}', { status: 503 })) : realFetch(url, options);
      await editorTheme.loadEditorThemes();
      check([...editorTheme.entries.keys()].join() === before, 'A failed refresh discarded installed themes');
    });
    await run('late startup preference cannot override a newer user selection', async () => {
      let complete;
      window.fetch = (url, options) => String(url) === EDITOR_PREFS_API && options?.method !== 'POST'
        ? new Promise(resolve => { complete = () => resolve(new Response('{"theme":"whiteout"}')); }) : realFetch(url, options);
      const pending = editorTheme.loadEditorThemePreference();
      editorTheme.applyEditorTheme('dark');
      complete(); await pending;
      check(document.documentElement.dataset.editorTheme === 'dark', 'Late preference overwrote user selection');
    });
    await run('failed save keeps the preview open and controls usable', async () => {
      editorTheme.applyEditorTheme('blackout'); editorTheme.openThemeAdjustDialog();
      const before = editorSettings.getItem('kloudyFabricTheme');
      window.fetch = (url, options) => String(url) === EDITOR_THEMES_API && options?.method === 'POST'
        ? Promise.resolve(new Response('{"error":"Test storage unavailable"}', { status: 503 })) : realFetch(url, options);
      await editorTheme.saveAdjustedTheme();
      check($('themeAdjustDialog').open, 'Failed save dismissed editing');
      check(!$('saveThemeAdjust').disabled && !$('themeAdjustName').disabled, 'Save left controls disabled');
      check(editorSettings.getItem('kloudyFabricTheme') === before, 'Failed save changed the selected theme');
    });
    await run('user choice during the initial theme-list request wins over all later startup work', async () => {
      let complete;
      const data = await (await realFetch(EDITOR_THEMES_API)).json();
      window.fetch = (url, options) => String(url) === EDITOR_THEMES_API
        ? new Promise(resolve => { complete = () => resolve(new Response(JSON.stringify(data))); }) : realFetch(url, options);
      const pending = editorTheme.initialize('pastel');
      editorTheme.applyEditorTheme('blackout');
      complete(); await pending;
      check(document.documentElement.dataset.editorTheme === 'blackout', 'List-stage startup overwrote the user choice');
    });
    await run('older list reply cannot forget a theme saved while it was pending', async () => {
      let complete;
      const oldList = await (await realFetch(EDITOR_THEMES_API)).json();
      window.fetch = (url, options) => String(url) === EDITOR_THEMES_API && options?.method !== 'POST'
        ? new Promise(resolve => { complete = () => resolve(new Response(JSON.stringify(oldList))); }) : realFetch(url, options);
      const pending = editorTheme.loadEditorThemes();
      editorTheme.openThemeAdjustDialog(); $('themeAdjustName').value = 'Newer than list';
      await editorTheme.saveAdjustedTheme();
      const savedId = editorSettings.getItem('kloudyFabricTheme');
      complete(); await pending;
      check(editorTheme.entries.has(savedId), 'Late list removed the just-saved theme');
      check($('editorThemeSelect').value === savedId, 'Late list changed selection');
    });
    await run('post-commit canvas refresh failure does not turn a saved theme into a failed save', async () => {
      editorTheme.openThemeAdjustDialog(); $('themeAdjustName').value = 'Saved despite display fault';
      const refresh = styleAllTransformControls;
      let injected = false;
      styleAllTransformControls = () => { injected = true; throw Error('Injected theme display failure'); };
      try { await editorTheme.saveAdjustedTheme(); }
      finally { styleAllTransformControls = refresh; }
      check(injected, 'Display fault was not injected');
      check(!$('themeAdjustDialog').open, 'Committed dialog was kept open as a failed save');
      check($('status').textContent.includes('Saved custom editor theme'), 'Committed theme reported a failed save');
      const savedId = editorSettings.getItem('kloudyFabricTheme');
      const saved = await (await realFetch(EDITOR_THEMES_API)).json();
      check(saved.themes.some(theme => theme.id === savedId), 'Selected theme does not exist on disk');
    });
    await run('terminal owner cleanup aborts I/O and ignores an uncancellable late reply', async () => {
      let complete, signal;
      window.fetch = (url, options) => String(url) === EDITOR_PREFS_API
        ? new Promise(resolve => { signal = options.signal; complete = () => resolve(new Response('{"theme":"whiteout"}')); }) : realFetch(url, options);
      const before = document.documentElement.dataset.editorTheme;
      const pending = editorTheme.loadEditorThemePreference();
      editorTheme.dispose(); editorTheme.dispose();
      await pending;
      check(signal.aborted, 'Cleanup did not abort the request');
      complete(); await new Promise(resolve => setTimeout(resolve, 20));
      editorTheme.applyEditorTheme('whiteout');
      check(document.documentElement.dataset.editorTheme === before, 'Closed owner changed visible state');
    });
    return results;
  });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  if (results.some(result => !result.passed)) throw Error(JSON.stringify(results));
  return results;
}
