async page => page.evaluate(async () => {
  editorTheme.applyEditorTheme('whiteout');
  await KfpsEditorPreferences.flush();
  const before = editorSettings.getItem('kloudyFabricTheme');
  editorTheme.applyEditorTheme('blackout', { persist: false });
  await KfpsEditorPreferences.flush();
  const after = editorSettings.getItem('kloudyFabricTheme');
  const stored = await (await fetch(EDITOR_PREFS_API)).json();
  if (before !== after || stored.settings.kloudyFabricTheme !== before) {
    throw new Error(`A non-persistent render changed the saved theme: ${JSON.stringify({ before, after, stored })}`);
  }
  if (document.documentElement.dataset.editorTheme !== 'blackout') throw new Error('Non-persistent theme did not render');
  editorTheme.applyEditorTheme('pastel', { preview: true });
  await KfpsEditorPreferences.flush();
  if (editorSettings.getItem('kloudyFabricTheme') !== before) throw new Error('Preview changed the saved theme');
  return { rendered: true, preferencePreserved: true, previewPreserved: true };
})
