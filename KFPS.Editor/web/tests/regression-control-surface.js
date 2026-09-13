async (page, options = {}) => {
  if (options.project) await require(path.join(__dirname, "handmade-project-fixture.cjs")).setup(page, output, options);
  return page.evaluate(async () => {
  const controls = new Map();
  function capture(stage) {
    for (const element of document.querySelectorAll('button,input,select,textarea,[role="button"],[role="tab"],[data-numeric-for]')) {
      const data = Object.fromEntries(Object.entries(element.dataset).filter(([key]) => ['tool', 'panel', 'numericFor', 'field', 'themeField', 'action'].includes(key)));
      const label = element.getAttribute('aria-label') || element.getAttribute('title') || element.labels?.[0]?.textContent?.trim() || element.textContent.trim().slice(0, 100);
      const key = element.id || `${element.tagName}:${JSON.stringify(data)}:${label}`;
      if (!controls.has(key)) controls.set(key, { key, id: element.id, tag: element.tagName, type: element.type || '',
        label, data, region: element.closest('dialog,[id$="Pane"]')?.id || 'shell', stage, disabled: Boolean(element.disabled) });
    }
  }
  capture('initial');
  editorTheme.openThemeAdjustDialog(); capture('theme adjustment'); editorTheme.closeThemeAdjustDialog();
  await openProjectBrowser(); capture('project browser');
  document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
  await openJsonBrowser(); capture('JSON browser');
  document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
  return { purpose: 'Reachable control inventory, not a claim of exhaustive behavior coverage', controls: [...controls.values()] };
  });
}
