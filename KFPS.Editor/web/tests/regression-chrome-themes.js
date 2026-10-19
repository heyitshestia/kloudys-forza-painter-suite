async (page, options = {}) => {
  if (options.chromeThemeRestartOnly) {
    const info = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
    const stateFile = path.join(info.profile, 'workspace-theme-state.json');
    const saved = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    const target = options.workspaceThemeRestart, next = options.workspaceThemeRestartNext || target;
    if (saved.pid === info.pid || !saved.custom[target] || !saved.custom[next]) throw Error('Fresh-process theme fixture is invalid');
    const rows = [];
    const verify = async (name, startup = false) => {
      const actual = await page.evaluate(() => ({ id: editorSettings.getItem('kloudyFabricTheme'),
        theme: document.documentElement.dataset.editorTheme, base: document.documentElement.dataset.editorThemeBase,
        values: editorTheme.themeFieldCurrentValues(), canvas: canvas.backgroundColor }));
      const expected = saved.custom[name];
      if (actual.id !== expected.id || actual.theme !== expected.theme || actual.base !== expected.base
        || Object.keys(actual.values).length !== 33 || Object.keys(expected.values).some(key => actual.values[key] !== expected.values[key])
        || actual.canvas !== actual.values['--fabric-canvas-bg']) throw Error('Fresh-process custom theme changed: ' + name);
      rows.push({ name, startup, exact33Colors: true, canvasMatched: true });
    };
    const select = async name => {
      await page.locator('#workspaceViewMenu').click();
      await page.locator('#editorThemeSelect').selectOption(saved.custom[name].id);
      await page.keyboard.press('Escape');
      await page.evaluate(() => KfpsEditorPreferences.flush());
    };
    await page.setViewportSize({ width: 1600, height: 1000 });
    await verify(target, true);
    if (!await page.locator('[data-panel-frame="propertiesPane"]').isVisible()) throw Error('Fresh-process floating panel was lost');
    for (const name of Object.keys(saved.custom)) {
      await select(name); await verify(name);
      await page.locator('#workspaceZoomIn').hover();
      await page.waitForFunction(() => document.getElementById('workspaceZoomIn').getAttribute('aria-describedby')?.includes('workspaceTooltip')
        && document.getElementById('workspaceTooltip').matches(':popover-open')
        && document.getElementById('workspaceTooltip').textContent === document.getElementById('workspaceZoomIn').dataset.workspaceTooltip);
      await page.screenshot({ path: path.join(output, `fresh-custom-${name}.png`) });
      await page.keyboard.press('Escape');
    }
    await select(next);
    saved.selected = next; saved.pid = info.pid;
    fs.writeFileSync(stateFile, JSON.stringify(saved, null, 2));
    const result = { passed: true, freshProcess: true, target, next, rows, floatingPanelPreserved: true,
      tooltipVisibleOwnerMatched: true, limitation: 'Targeted fresh-process check; does not replace the broader shared theme suite' };
    fs.writeFileSync(path.join(output, 'chrome-theme-restart.json'), JSON.stringify(result, null, 2));
    return result;
  }
  const withRecovery = require(path.join(__dirname, 'chrome-reload-adapter.cjs'));
  const source = fs.readFileSync(path.join(__dirname, 'regression-workspace-themes.js'), 'utf8');
  const run = eval(`(${source})`);
  return withRecovery(page, output, () => run(page, options));
}
