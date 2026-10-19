async (page, options = {}) => {
  const fs = require('node:fs');
  const crypto = require('node:crypto');
  const appRoot = process.env.KFPS_TEST_APP_ROOT || path.resolve(__dirname, '../../..');
  const webRoot = path.join(appRoot, 'KFPS.Editor/web');
  const processInfo = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
  const stateFile = path.join(processInfo.profile, 'workspace-theme-state.json');
  const hash = value => crypto.createHash('sha256').update(value).digest('hex');
  const check = (condition, message) => { if (!condition) throw Error(message); };
  const findings = [], identities = [], themes = [], layouts = [];
  const record = (condition, message, detail) => {
    if (!condition) {
      findings.push({ message, detail });
      fs.writeFileSync(path.join(output, 'workspace-theme-findings.json'), JSON.stringify(findings, null, 2));
    }
  };
  page.setDefaultTimeout(20000);

  // Manual inventory includes the wrapper calls and labels passed through button().
  const workspaceLabels = [
    'File', 'Edit', 'View', 'Help', 'Reset workspace', 'Cycle overlaps', 'Artwork canvas',
    'Untitled vinyl', 'Layer and group actions', 'Filter layers by name, type, or number',
    'Corner handles preserve proportions; side handles resize one axis. Shift-corner skews. Numeric scales are independent.',
    'Proportional corners', 'Inspector panels', 'Resize inspector width', 'Zoom out', 'Zoom in', 'Fit Vinyl',
  ];
  // Frozen compatibility contract, not derived from the implementation under test.
  const themeKeys = [
    '--bg', '--shell', '--panel', '--panel2', '--panel3', '--text', '--muted', '--soft',
    '--line', '--line2', '--accent', '--accent2', '--good', '--warn', '--danger', '--canvas-bg',
    '--fabric-canvas-bg', '--editor-grid-line', '--editor-grid-axis', '--editor-guide-line',
    '--editor-guide-selected', '--editor-guide-draft', '--editor-notch-line', '--editor-notch-muted',
    '--editor-notch-active', '--editor-selection-border', '--editor-shape-outline',
    '--editor-selection-corner', '--editor-selection-corner-stroke', '--editor-skew-corner',
    '--shape-tile-bg', '--dialog-bg', '--dialog-header',
  ].sort();
  const sameKeys = values => JSON.stringify(Object.keys(values).sort()) === JSON.stringify(themeKeys);
  const sameColors = (a, b) => themeKeys.every(key => a[key] === b[key]);
  const catalog = Object.fromEntries(['en', 'ko'].map(lang => [lang,
    JSON.parse(fs.readFileSync(path.join(webRoot, `locales/${lang}.json`), 'utf8'))]));
  const workspaceSource = fs.readFileSync(path.join(webRoot, 'editor-workspace.js'), 'utf8');
  const directLabels = [...workspaceSource.matchAll(/\bt\('([^'\\]*)'\)/g)].map(match => match[1]);
  const buttonLabels = [...workspaceSource.matchAll(/\bbutton\('[^'\\]*',\s*'([^'\\]*)'/g)].map(match => match[1]);
  check([...directLabels, ...buttonLabels].every(label => workspaceLabels.includes(label)),
    'Workspace labels changed: review and update the manual localization inventory');
  for (const label of workspaceLabels) {
    check(catalog.en.messages[label] === label, `Missing authoritative English label: ${label}`);
    check(typeof catalog.ko.messages[label] === 'string' && /[\uac00-\ud7a3]/.test(catalog.ko.messages[label]),
      `Missing Korean workspace label: ${label}`);
  }

  async function sourceIdentity(stage) {
    const session = await page.context().newCDPSession(page);
    const parsed = new Map(), sheets = new Map();
    const scripts = ['editor-workspace.js', 'editor-themes.js', 'locales/en.js', 'locales/ko.js'];
    session.on('Debugger.scriptParsed', entry => {
      const name = scripts.find(name => entry.url.split('?')[0].endsWith('/' + name));
      if (name) parsed.set(name, entry.scriptId);
    });
    session.on('CSS.styleSheetAdded', ({ header }) => {
      if (header.sourceURL.split('?')[0].endsWith('/workspace.css')) sheets.set('workspace.css', header.styleSheetId);
    });
    try {
      await session.send('Debugger.enable');
      await session.send('DOM.enable');
      await session.send('CSS.enable');
      for (const name of [...scripts, 'workspace.css']) {
        const disk = fs.readFileSync(path.join(webRoot, name), 'utf8');
        check(name.endsWith('.css') ? sheets.has(name) : parsed.has(name), `Missing loaded source: ${name}`);
        const loaded = name.endsWith('.css')
          ? (await session.send('CSS.getStyleSheetText', { styleSheetId: sheets.get(name) })).text
          : (await session.send('Debugger.getScriptSource', { scriptId: parsed.get(name) })).scriptSource;
        const item = { stage, name, expected: hash(disk), actual: hash(loaded), matched: disk === loaded };
        identities.push(item);
        check(item.matched, `Stale or concurrently changed ${name} during ${stage}`);
        const destination = path.join(output, 'workspace-sources', name);
        fs.mkdirSync(path.dirname(destination), { recursive: true });
        fs.writeFileSync(destination, disk);
      }
    } finally {
      fs.writeFileSync(path.join(output, 'workspace-source-identity.json'), JSON.stringify(identities, null, 2));
      await session.send('CSS.disable');
      await session.send('DOM.disable');
      await session.send('Debugger.disable');
      await session.detach();
    }
  }

  async function openView() {
    if (!await page.locator('#workspaceViewCommands').evaluate(node => node.matches(':popover-open'))) {
      await page.locator('#workspaceViewMenu').click();
    }
  }
  async function closeMenu() {
    if (await page.locator('.workspaceMenu:popover-open').count()) await page.keyboard.press('Escape');
  }
  async function selectTheme(id) {
    await openView();
    await page.locator('#editorThemeSelect').selectOption(id);
    await closeMenu();
    await page.evaluate(() => KfpsEditorPreferences.flush());
  }
  async function adjust() {
    await openView();
    await page.locator('#adjustTheme').click();
    await page.locator('#themeAdjustDialog').waitFor({ state: 'visible' });
  }
  async function state() {
    return page.evaluate(() => ({
      id: editorSettings.getItem('kloudyFabricTheme'), theme: document.documentElement.dataset.editorTheme,
      base: document.documentElement.dataset.editorThemeBase, values: editorTheme.themeFieldCurrentValues(),
      canvas: canvas.backgroundColor, matte: getComputedStyle(document.body).backgroundImage === 'none',
    }));
  }
  async function assertState(expected, label) {
    const actual = await state();
    check(actual.id === expected.id && actual.base === expected.base && actual.theme === expected.theme,
      `${label}: selection changed: ${JSON.stringify(actual)}`);
    check(sameColors(actual.values, expected.values), `${label}: colors did not round-trip`);
    check(actual.canvas === actual.values['--fabric-canvas-bg'], `${label}: canvas did not adopt theme color`);
    return actual;
  }

  async function tokenBindings(label) {
    await openView();
    const bindings = await page.evaluate(() => {
      const probe = document.createElement('span'); document.body.append(probe);
      const tests = [
        ['.appBar', 'backgroundColor', '--shell'], ['.contextBar', 'backgroundColor', '--panel'],
        ['.toolRail', 'backgroundColor', '--shell'], ['.workspaceMenu:popover-open', 'backgroundColor', '--panel'],
        ['.workspaceMenu:popover-open', 'borderTopColor', '--line2'],
        ['.workspaceMenu:popover-open', 'color', '--text'], ['.workspaceZoom', 'backgroundColor', '--panel'],
        ['.workspaceZoom', 'borderTopColor', '--line2'], ['#bottomZoom', 'color', '--text'],
        ['.workspaceLayerSearch svg', 'color', '--muted'], ['.workspaceDisclosure summary', 'color', '--text'],
        ['.dockTab.active', 'borderBottomColor', '--accent'], ['.dockTab.active', 'backgroundColor', '--panel'],
        ['#workspaceTooltip', 'backgroundColor', '--panel'], ['#workspaceTooltip', 'color', '--text'],
      ];
      if (document.querySelector('.workspaceFloatingPanel')) tests.push(
        ['.workspaceFloatingPanel', 'backgroundColor', '--panel'],
        ['.workspaceFloatingPanel', 'color', '--text'],
        ['.workspaceFloatingPanel', 'borderTopColor', '--line2'],
        ['.workspaceFloatingPanel .workspacePanelResize', 'color', '--muted']);
      const result = tests.map(([selector, property, token]) => {
        const node = document.querySelector(selector);
        probe.style.color = `var(${token})`;
        const expected = getComputedStyle(probe).color;
        const actual = node && getComputedStyle(node)[property];
        return { selector, property, token, expected, actual, matched: actual === expected };
      });
      probe.remove(); return result;
    });
    for (const binding of bindings) record(binding.matched, `${label}: workspace token mismatch`, binding);
    await closeMenu();
    await page.locator('#workspaceZoomIn').hover();
    const tooltip = await page.locator('#workspaceTooltip').innerText();
    record(await page.locator('#workspaceTooltip').isVisible() && tooltip === await page.locator('#workspaceZoomIn').getAttribute('data-workspace-tooltip'),
      `${label}: zoom tooltip missing or stale`, tooltip);
    await page.keyboard.press('Escape');
    return bindings;
  }

  async function geometry(label, size) {
    await page.setViewportSize(size);
    await openView();
    const measure = await page.evaluate(() => {
      const nodes = ['.appBar', '#workspaceViewCommands', '.workspaceZoom', '.canvasStage', '.rightDock'];
      const boxes = nodes.map(selector => {
        const node = document.querySelector(selector), r = node.getBoundingClientRect();
        return { selector, x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom,
          scrollWidth: node.scrollWidth, clientWidth: node.clientWidth };
      });
      return { width: innerWidth, height: innerHeight, scrollWidth: document.documentElement.scrollWidth,
        scrollHeight: document.documentElement.scrollHeight, boxes };
    });
    record(measure.scrollWidth <= size.width && measure.scrollHeight <= size.height,
      `${label}: document overflow at ${size.width}x${size.height}`, measure);
    for (const box of measure.boxes.filter(box => ['#workspaceViewCommands', '.workspaceZoom'].includes(box.selector))) {
      record(box.x >= 0 && box.y >= 0 && box.right <= size.width + 1 && box.bottom <= size.height + 1 && box.scrollWidth <= box.clientWidth + 1,
        `${label}: control overflow at ${size.width}x${size.height}`, box);
    }
    await page.screenshot({ path: path.join(output, `${label}-${size.width}-menu.png`) });
    await page.locator('#adjustTheme').click();
    const dialog = await page.locator('#themeAdjustDialog').evaluate(node => {
      const r = node.getBoundingClientRect();
      return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, scroll: node.scrollWidth, client: node.clientWidth };
    });
    record(dialog.x >= 0 && dialog.y >= 0 && dialog.right <= size.width + 1 && dialog.bottom <= size.height + 1 && dialog.scroll <= dialog.client + 1,
      `${label}: theme dialog overflow at ${size.width}x${size.height}`, dialog);
    await page.screenshot({ path: path.join(output, `${label}-${size.width}-adjust.png`) });
    await page.locator('#closeThemeAdjust').click();
    const hitZoom = () => page.locator('#workspaceZoomIn').evaluate(node => {
      const r = node.getBoundingClientRect();
      const target = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
      return { reachable: Boolean(target && node.contains(target)), interceptedBy: target?.id || target?.className,
        floatingPanel: target?.closest('[data-panel-frame]')?.dataset.panelFrame };
    });
    let zoomHit = await hitZoom();
    if (!zoomHit.reachable && zoomHit.floatingPanel) {
      // User-positioned floats can cover canvas tools. Verify their real recovery control.
      const collapse = page.locator(`[data-panel-frame="${zoomHit.floatingPanel}"] [data-collapse]`);
      const occlusion = zoomHit;
      await collapse.click(); zoomHit = { ...await hitZoom(), recoveredByCollapsing: occlusion.floatingPanel };
      await collapse.click();
    }
    record(zoomHit.reachable, `${label}: zoom control occluded at ${size.width}x${size.height}`, zoomHit);
    layouts.push({ label, ...size, measure, dialog, zoomHit });
  }

  await page.waitForFunction(() => window.KfpsDesktop?.ready && window.KfpsWorkspace && document.documentElement.classList.contains('workspaceRedesign'));
  const display = {
    qtScaleFactor: processInfo.qtScaleFactor,
    qtScreens: processInfo.screens,
    nativeDevicePixelRatio: await page.evaluate(() => devicePixelRatio),
  };
  await page.setViewportSize({ width: 1600, height: 1000 });
  if (options.workspaceThemeDocking && !options.workspaceThemeRestart) {
    await page.locator('.dockTab[data-panel="propertiesPane"]').click({ button: 'right' });
    await page.locator('[data-dock-action="float"]').click();
    check(await page.locator('[data-panel-frame="propertiesPane"]').isVisible(), 'Properties did not detach before theme roundtrip');
  }
  if (options.workspaceThemeDocking && options.workspaceThemeRestart) {
    check(await page.locator('[data-panel-frame="propertiesPane"]').isVisible(), 'Fresh host lost floating theme test panel');
  }
  display.testDevicePixelRatio = await page.evaluate(() => devicePixelRatio);
  await sourceIdentity('startup');
  const initial = await state();
  check(sameKeys(initial.values), 'Theme format must retain exactly the existing 33 keys');

  let saved;
  if (options.workspaceThemeRestart) {
    check(fs.existsSync(stateFile), 'Fresh-host check requires the first run isolated profile');
    saved = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    check(saved.pid !== processInfo.pid, 'Restart check must use a new native host process');
    const target = typeof options.workspaceThemeRestart === 'string' ? options.workspaceThemeRestart : saved.selected;
    check(saved.custom[target], `Unknown restart target: ${target}`);
    await assertState(saved.custom[target], `Fresh host ${target}`);
    for (const [name, expected] of Object.entries(saved.custom)) {
      await selectTheme(expected.id);
      await assertState(expected, `Load saved ${name}`);
      themes.push({ name, restart: true, bindings: await tokenBindings(name) });
    }
    const next = options.workspaceThemeRestartNext || target;
    check(saved.custom[next], `Unknown next restart target: ${next}`);
    await selectTheme(saved.custom[next].id);
    saved.selected = next;
    saved.pid = processInfo.pid;
    fs.writeFileSync(stateFile, JSON.stringify(saved, null, 2));
  } else {
    await page.evaluate(async () => {
      await loadPayload({ shapes: Array.from({ length: 24 }, (_, i) => ({
        type: 1048677 + i % 8, color: [80 + i * 5, 110, 160, 255],
        data: [(i % 6) * 120 - 300, Math.floor(i / 6) * 120 - 180, .7, .7, i * 9, 0, 0],
      })) });
    });
    for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) {
      await selectTheme(theme);
      const before = await state();
      check(before.id === theme && before.base === theme && before.theme === theme, `${theme} did not apply`);
      const bindings = await tokenBindings(theme);
      await page.screenshot({ path: path.join(output, `${theme}-workspace.png`) });
      await adjust();
      check(await page.locator('.themeValueInput:visible').count() === 6, `${theme}: expected six basic colors`);
      const fields = await page.locator('.themeValueInput').evaluateAll(nodes => Object.fromEntries(nodes.map(node => [node.dataset.themeVar, node.value])));
      check(sameKeys(fields), `${theme}: theme editor changed the 33-key format`);
      await page.locator('[data-theme-var="--text"]').fill('invalid-color');
      check(await page.locator('#saveThemeAdjust').isDisabled(), `${theme}: invalid color can save`);
      await page.locator('#resetThemeAdjust').click();
      check(await page.locator('[data-theme-var="--text"]').inputValue() === before.values['--text'], `${theme}: reset failed`);
      await page.locator('.themeAdvanced summary').click();
      check(await page.locator('.themeValueInput:visible').count() === 33, `${theme}: advanced colors inaccessible`);
      await page.locator('#themeAdjustBase').selectOption(theme === 'whiteout' ? 'blackout' : 'whiteout');
      await page.locator('[data-theme-var="--accent"]').fill('#12a7b3');
      check((await state()).id === theme, `${theme}: preview persisted selection`);
      check((await state()).values['--accent'] === '#12a7b3', `${theme}: preview did not apply`);
      if (theme === 'dark' || theme === 'whiteout') await page.locator('#closeThemeAdjust').click();
      else await page.locator('#themeAdjustName').press('Escape');
      await assertState(before, `${theme} cancel`);
      themes.push({ name: theme, bindings, previewCancel: true, validation: true, formatKeys: 33 });
    }

    saved = { pid: processInfo.pid, selected: 'light', custom: {} };
    for (const [name, base, colors] of [
      ['dark', 'blackout', { '--shell': '#191d22', '--panel': '#232a31', '--text': '#f4f7fa', '--accent': '#8dd5c1', '--line': '#8796a4', '--fabric-canvas-bg': '#253039' }],
      ['light', 'whiteout', { '--shell': '#f1f5f7', '--panel': '#e8eef2', '--text': '#202b35', '--accent': '#146b57', '--line': '#596a79', '--fabric-canvas-bg': '#dae7ee' }],
    ]) {
      await adjust();
      await page.locator('#themeAdjustBase').selectOption(base);
      await page.locator('#themeAdjustName').fill(`Workspace QA ${name}`);
      for (const [key, value] of Object.entries(colors)) await page.locator(`[data-theme-var="${key}"]`).fill(value);
      const preview = await state();
      await page.locator('#saveThemeAdjust').click();
      await page.locator('#themeAdjustDialog').waitFor({ state: 'hidden' });
      await page.evaluate(() => KfpsEditorPreferences.flush());
      const custom = await state();
      check(custom.theme === 'custom' && custom.base === base && custom.matte && sameKeys(custom.values), `${name}: custom theme not applied`);
      check(sameColors(custom.values, preview.values), `${name}: save changed preview colors`);
      saved.custom[name] = custom;
      themes.push({ name: `custom-${name}`, bindings: await tokenBindings(`custom-${name}`) });
      await page.screenshot({ path: path.join(output, `custom-${name}-workspace.png`) });
      const themeFile = path.join(processInfo.profile, 'themes', custom.id + '.json');
      check(fs.existsSync(themeFile), `${name}: no saved theme artifact in isolated profile`);
      const artifact = JSON.parse(fs.readFileSync(themeFile, 'utf8'));
      check(artifact.format === 'kfps_fabric_editor_theme_v1' && sameKeys(artifact.values) && artifact.base === base && sameColors(artifact.values, custom.values),
        `${name}: saved theme artifact lost colors or changed schema`);
      await selectTheme('pastel');
      await selectTheme(custom.id);
      await assertState(custom, `${name} reapply`);
    }

    await page.locator('#workspaceFileMenu').click();
    await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill('Workspace theme persistence');
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    await page.evaluate(async () => { await KfpsEditorPreferences.flush(); await flushPendingAutosave(); });
    await page.reload();
    await page.waitForFunction(() => window.KfpsDesktop?.ready && document.documentElement.dataset.editorTheme === 'custom');
    await assertState(saved.custom.light, 'Reload custom light');
    await sourceIdentity('reload');
    for (const size of [{ width: 1600, height: 1000 }, { width: 900, height: 640 }, { width: 760, height: 640 }]) {
      await geometry('en', size);
    }
    await page.evaluate(async () => { KfpsEditorPreferences.setItem('kloudyFabricLanguage', 'ko'); await KfpsEditorPreferences.flush(); });
    await page.reload();
    await page.waitForFunction(() => window.KfpsDesktop?.ready && window.KfpsWorkspace && document.documentElement.lang === 'ko');
    await page.setViewportSize({ width: 1600, height: 1000 });
    const localized = await page.evaluate(() => {
      const read = (selector, attribute) => attribute ? document.querySelector(selector)?.getAttribute(attribute) : document.querySelector(selector)?.textContent.trim();
      return [
        ['#workspaceFileMenu', null, 'File'], ['#workspaceEditMenu', null, 'Edit'],
        ['#workspaceViewMenu', null, 'View'], ['#workspaceHelpMenu', null, 'Help'],
        ['#workspaceReset', null, 'Reset workspace'], ['.workspaceOverlap', null, 'Cycle overlaps'],
        ['.canvasStage', 'aria-label', 'Artwork canvas'], ['#groupActions', 'aria-label', 'Layer and group actions'],
        ['#layerSearch', 'aria-label', 'Filter layers by name, type, or number'],
        ['#workspaceDockWidth', 'data-workspace-tooltip', 'Resize inspector width'], ['.inspectorDock > .dockTabs', 'aria-label', 'Inspector panels'],
        ['#workspaceZoomIn', 'data-workspace-tooltip', 'Zoom in'], ['#workspaceZoomOut', 'data-workspace-tooltip', 'Zoom out'],
        ['#workspaceFit', 'data-workspace-tooltip', 'Fit Vinyl'], ['.workspaceTransformMode', null, 'Proportional corners'],
        ['.workspaceTransformMode', 'data-workspace-tooltip', 'Corner handles preserve proportions; side handles resize one axis. Shift-corner skews. Numeric scales are independent.'],
      ].map(([selector, attribute, key]) => ({ selector, attribute, key, actual: read(selector, attribute), expected: KfpsI18n.t(key) }));
    });
    for (const item of localized) record(item.actual === item.expected, 'Korean workspace label mismatch', item);
    await tokenBindings('ko');
    for (const size of [{ width: 1600, height: 1000 }, { width: 900, height: 640 }, { width: 760, height: 640 }]) {
      await geometry('ko', size);
    }
    await page.setViewportSize({ width: 1600, height: 1000 });
    await selectTheme(saved.custom[options.workspaceThemeRestartTarget || 'light'].id);
    saved.selected = options.workspaceThemeRestartTarget || 'light';
    await page.evaluate(async () => { KfpsEditorPreferences.setItem('kloudyFabricLanguage', 'en'); await KfpsEditorPreferences.flush(); });
    fs.writeFileSync(stateFile, JSON.stringify(saved, null, 2));
  }
  await page.evaluate(async () => { await KfpsEditorPreferences.flush(); await flushPendingAutosave(); });
  await sourceIdentity('complete');
  const report = { passed: findings.length === 0, findings, themes, layouts, identities, manualLabels: workspaceLabels,
    themeKeys, display, freshHostRestart: Boolean(options.workspaceThemeRestart), savedState: stateFile, saved };
  fs.writeFileSync(path.join(output, 'workspace-theme-report.json'), JSON.stringify(report, null, 2));
  return report;
}
