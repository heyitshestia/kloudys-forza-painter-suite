async (page, options = {}) => {
  const fs = require('node:fs');
  const crypto = require('node:crypto');
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const section = options.dockingEdgesSection || 'gestures';
  const webRoot = path.join(process.env.KFPS_TEST_APP_ROOT, 'KFPS.Editor/web');
  const findings = [], cases = [], measurements = [];
  const hash = value => crypto.createHash('sha256').update(value).digest('hex');
  const sources = Object.fromEntries(['editor-docking.js', 'editor-workspace.js', 'workspace.css', 'locales/en.js', 'locales/ko.js']
    .map(name => [name, hash(fs.readFileSync(path.join(webRoot, name)))]));
  for (const name of Object.keys(sources)) {
    const target = path.join(output, 'docking-sources', name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.copyFileSync(path.join(webRoot, name), target);
  }
  const check = (ok, message, detail) => { if (!ok) throw Error(message + (detail ? ': ' + JSON.stringify(detail) : '')); };
  const reportFile = path.join(output, 'docking-edges-report.json');
  const write = () => fs.writeFileSync(reportFile, JSON.stringify({ section, sources, cases, findings, measurements }, null, 2));
  const tab = id => page.locator(`.dockTab[data-panel="${id}"]`);
  const frame = id => page.locator(`[data-panel-frame="${id}"]`);
  const place = id => page.locator(`#${id}`).getAttribute('data-dock-place');
  const snapshot = () => page.evaluate(() => ({ shapes: JSON.stringify(snapshotShapes()),
    history: JSON.stringify({ entries: editorHistory.entries, index: editorHistory.index, floor: editorHistory.floor, sequence: editorHistory.sequence }) }));
  const closeMenus = async () => {
    for (let i = 0; i < 3 && await page.locator('.workspaceMenu:popover-open').count(); i++) await page.keyboard.press('Escape');
  };
  const view = async id => {
    await closeMenus();
    await page.locator('#workspaceViewMenu').click();
    await page.locator(`#${id}`).click();
  };
  const choose = async (id, action) => {
    await closeMenus();
    const handle = id === 'layersPane' && !await tab(id).isVisible() ? page.locator('#layersPane h2') : tab(id);
    await handle.click({ button: 'right' });
    await page.locator(`[data-dock-action="${action}"]`).click();
  };
  const show = async id => { await view('workspacePanels'); await page.locator(`[data-show-panel="${id}"]`).click(); };
  const center = async locator => {
    const box = await locator.boundingBox(); check(box, 'Missing pointer target');
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  };
  const drag = async (locator, to, cancel) => {
    const from = await center(locator);
    await page.mouse.move(from.x, from.y); await page.mouse.down();
    try {
      await page.mouse.move(to.x, to.y, { steps: 6 });
      if (cancel === 'Escape') await page.keyboard.press('Escape');
      // Only window deactivation is injected; the pointer gesture itself is real CDP input.
      if (cancel === 'blur') await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    } finally { await page.mouse.up(); }
  };
  const cleanDrag = async () => check(await page.locator('.workspacePanelGhost,.panelDragging').count() === 0, 'Gesture left drag UI behind');
  const rect = async id => frame(id).evaluate(node => ({ x: node.style.left, y: node.style.top, width: node.style.width, height: node.style.height }));
  let baseline;
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const unchanged = async (before, label) => {
    await page.waitForFunction(() => !editorCommands.busy);
    const after = await snapshot();
    if (after.shapes !== before.shapes || after.history !== before.history) {
      fs.writeFileSync(path.join(output, `state-difference-${cases.length}.json`), JSON.stringify({ label, before, after }, null, 2));
      check(after.shapes === before.shapes, `${label}: changed exact artwork`);
      check(after.history === before.history, `${label}: changed undo history`);
    }
  };
  async function run(name, action, reset = true) {
    if (options.dockingEdgeCases && !options.dockingEdgeCases.some(part => name.includes(part))) return;
    console.log('docking-edges: ' + name);
    const start = Date.now();
    try {
      await closeMenus();
      if (reset) await page.evaluate(() => KfpsDocking.reset());
      const before = baseline && await snapshot();
      await action();
      await cleanDrag();
      if (baseline) await unchanged(before, name);
      cases.push({ name, passed: true, ms: Date.now() - start });
    } catch (error) {
      const failure = { name, error: String(error.stack || error), ms: Date.now() - start };
      cases.push({ ...failure, passed: false }); findings.push(failure);
      await page.mouse.up();
      await page.screenshot({ path: path.join(output, `failure-${cases.length}.png`), timeout: 8000 }).catch(() => {});
    }
    write();
  }
  page.setDefaultTimeout(5000);
  await page.setViewportSize({ width: 1600, height: 1000 });
  const labels = ['Panel options', 'Collapse or expand panel', 'Close panel', 'Resize panel', 'Left panels',
    'Resize left panels', 'Float panel', 'Dock left', 'Dock right', 'Panels', 'Layers', 'Lock panel positions',
    'Focus canvas', 'Drag to move this panel. Right-click for panel options. Alt+arrow keys move a floating panel.'];
  for (const lang of ['en', 'ko']) {
    const catalog = JSON.parse(fs.readFileSync(path.join(webRoot, `locales/${lang}.json`), 'utf8'));
    for (const label of labels) check(lang === 'en' ? catalog.messages[label] === label : /[\uac00-\ud7a3]/.test(catalog.messages[label] || ''),
      `Missing ${lang} docking label: ${label}`);
  }
  const fixture = path.join(output, 'docking-12-shapes.json');
  fs.writeFileSync(fixture, JSON.stringify({ shapes: Array.from({ length: 12 }, (_, i) => ({
    type: [1048677, 1048678, 1048679][i % 3], color: [50 + i * 12, 160, 190, i % 3 ? 255 : 128],
    data: [-200 + i % 4 * 130, 150 - Math.floor(i / 4) * 130, .35, .4, i * 15, 0, 0],
    editor_id: `docking-${i}`, shape_name: `Dock shape ${i}`,
  })) }));
  await h.fileInput(page, '#jsonInput', fixture);
  await page.waitForFunction(() => vinylObjects().length === 12 && !recoveryRestoreDepth);
  await page.locator('#workspaceFit').click();
  await h.select(page, 'Dock shape 5');
  const original = (await snapshot()).shapes;
  await page.locator('#quickDuplicateLayer').click();
  await page.waitForFunction(() => vinylObjects().length === 13 && !editorCommands.busy);
  const duplicate = (await snapshot()).shapes;
  await page.locator('#undoBtn').click();
  await page.waitForFunction(() => vinylObjects().length === 12 && !editorCommands.busy);
  check((await snapshot()).shapes === original, 'Fixture duplicate did not undo exactly');
  await h.select(page, 'Dock shape 5');
  check(await page.evaluate(() => selectedVinylObjects().length) === 1, 'Keyboard safety requires a selected artwork target');
  baseline = await snapshot();

  if (section === 'gestures') {
    await run('tab drag floats original controls and docks left/right', async () => {
      await drag(tab('propertiesPane'), { x: 620, y: 280 });
      check(await place('propertiesPane') === 'floating', 'Tab drag did not float');
      await drag(tab('propertiesPane'), { x: 65, y: 310 });
      check(await place('propertiesPane') === 'left', 'Tab drag did not dock left');
      await drag(tab('propertiesPane'), { x: 1575, y: 300 });
      check(await place('propertiesPane') === 'home', 'Tab drag did not dock right');
      const duplicates = await page.evaluate(() => [...document.querySelectorAll('[id]')].map(n => n.id).filter((id, i, all) => all.indexOf(id) !== i));
      check(!duplicates.length, 'Moving original controls duplicated IDs', duplicates);
    });
    await run('tab reorder follows real drop target', async () => {
      const before = await page.locator('.inspectorDock .dockTab').evaluateAll(nodes => nodes.map(n => n.dataset.panel));
      await drag(tab(before.at(-1)), await center(tab(before[0])));
      const after = await page.locator('.inspectorDock .dockTab').evaluateAll(nodes => nodes.map(n => n.dataset.panel));
      check(after.join() === [before.at(-1), ...before.slice(0, -1)].join(), 'Tab order differs from requested insertion', { before, after });
    });
    for (const cancel of ['Escape', 'blur']) await run(`tab drag ${cancel} cancellation`, async () => {
      const before = await place('historyPane');
      await drag(tab('historyPane'), { x: 650, y: 300 }, cancel);
      check(await place('historyPane') === before, 'Cancelled tab moved');
      await tab('propertiesPane').click();
      check(await tab('propertiesPane').getAttribute('aria-selected') === 'true', 'Cancellation swallowed next click');
    });
    await run('left tool drag does not activate unrelated drawing tool', async () => {
      await page.locator('[data-tool-mode="select"]').click();
      const before = await page.evaluate(() => activeToolMode);
      await drag(page.locator('[data-tool-mode="text"]'), { x: 700, y: 260 });
      check(await place('textPane') === 'floating', 'Left tool drag did not float associated panel');
      check(await page.evaluate(() => activeToolMode) === before, 'Drag activated the text tool');
    });
    await run('floating resize commits and keyboard resize preserves artwork', async () => {
      await choose('propertiesPane', 'float');
      const before = await rect('propertiesPane');
      const handle = frame('propertiesPane').locator('[data-resize]'), point = await center(handle);
      await drag(handle, { x: point.x + 64, y: point.y + 48 });
      const after = await rect('propertiesPane');
      check(parseFloat(after.width) === parseFloat(before.width) + 64 && parseFloat(after.height) === parseFloat(before.height) + 48,
        'Floating resize did not follow pointer', { before, after });
      await handle.focus(); await page.keyboard.press('ArrowRight');
      check(parseFloat((await rect('propertiesPane')).width) === parseFloat(after.width) + 16, 'Keyboard resize failed');
    });
    for (const cancel of ['Escape', 'blur']) await run(`floating resize ${cancel} cancellation`, async () => {
      await choose('historyPane', 'float');
      const before = await rect('historyPane'), handle = frame('historyPane').locator('[data-resize]'), point = await center(handle);
      await drag(handle, { x: point.x + 75, y: point.y + 60 }, cancel);
      check(JSON.stringify(await rect('historyPane')) === JSON.stringify(before), 'Cancelled float resize was not restored');
    });
    await run('left dock resize and cancellation', async () => {
      await choose('propertiesPane', 'left');
      const handle = page.locator('.workspaceLeftResize'), point = await center(handle);
      await drag(handle, { x: point.x + 70, y: point.y });
      check(await handle.getAttribute('aria-valuenow') === '390', 'Left resize did not commit');
      for (const cancel of ['Escape', 'blur']) {
        const next = await center(handle); await drag(handle, { x: next.x - 50, y: next.y }, cancel);
        check(await handle.getAttribute('aria-valuenow') === '390', `Left resize ${cancel} did not restore`);
      }
      await handle.focus(); await page.keyboard.press('Home');
      check(await handle.getAttribute('aria-valuenow') === '320', 'Left resize Home failed');
    });
    await run('collapse expand close and View Panels recovery', async () => {
      await choose('historyPane', 'float');
      const collapse = frame('historyPane').locator('[data-collapse]');
      await collapse.click(); check(await collapse.getAttribute('aria-expanded') === 'false', 'Collapse ARIA state stale');
      check(!await page.locator('#historyPane').isVisible(), 'Collapsed pane still visible');
      await show('historyPane'); check(await page.locator('#historyPane').isVisible(), 'Panels did not expand floating panel');
      await frame('historyPane').getByRole('button', { name: 'Close panel', exact: true }).click();
      check(await place('historyPane') === 'hidden', 'Close did not park panel');
      await show('historyPane'); check(await place('historyPane') === 'home' && await page.locator('#historyPane').isVisible(), 'Panels did not reopen closed panel');
    });
    await run('layer header detach and original layer controls work', async () => {
      await drag(page.locator('#layersPane h2'), { x: 650, y: 250 });
      check(await place('layersPane') === 'floating', 'Layer header did not detach');
      await page.locator('#layerSearch').fill('Dock shape 7');
      await page.locator('.layerRow').filter({ hasText: 'Dock shape 7' }).click();
      check(await page.evaluate(() => selectedVinylObjects().length) === 1, 'Detached layer control did not select');
      await choose('layersPane', 'home');
      check(await page.locator('#layersPane').evaluate(n => !!n.closest('.layersDock')), 'Layers did not reattach');
    });
    await run('Shift F10 menu navigation and Escape return focus', async () => {
      await tab('historyPane').focus(); await page.keyboard.press('Shift+F10');
      check(await page.locator('#workspacePanelMenu').evaluate(n => n.matches(':popover-open')), 'Shift F10 did not open menu');
      await page.keyboard.press('End');
      check(await page.locator('[data-dock-action="hide"]').evaluate(n => n === document.activeElement), 'Menu End did not focus close');
      await page.keyboard.press('Home'); await page.keyboard.press('Enter');
      check(await place('historyPane') === 'floating', 'Keyboard menu did not float panel');
      await page.keyboard.press('Shift+F10'); await page.keyboard.press('Escape');
      check(await tab('historyPane').evaluate(n => n === document.activeElement), 'Escape did not restore tab focus');
    });
    await run('nested View Panels keyboard selection uses active submenu', async () => {
      await choose('historyPane', 'hide');
      await page.locator('#workspaceViewMenu').focus(); await page.keyboard.press('ArrowDown');
      await page.locator('#workspacePanels').focus(); await page.keyboard.press('Enter');
      await page.keyboard.press('End');
      const focused = await page.evaluate(() => ({ panel: document.activeElement.dataset.showPanel, id: document.activeElement.id }));
      check(focused.panel === 'layersPane', 'Nested Panels navigation escaped submenu', focused);
      await page.keyboard.press('Escape');
      check(await page.evaluate(() => ['workspacePanels', 'workspaceViewMenu'].includes(document.activeElement.id)
        && !!document.activeElement.getClientRects().length), 'Submenu Escape lost visible menu trigger',
      await page.evaluate(() => ({ focus: document.activeElement.id, menus: [...document.querySelectorAll('.workspaceMenu:popover-open')].map(n => n.id) })));
    });
    await run('floating Alt arrows stay scoped and locking blocks movement', async () => {
      await choose('historyPane', 'float');
      let before = await rect('historyPane');
      const artwork = await snapshot();
      await tab('historyPane').focus(); await page.keyboard.press('Alt+ArrowRight'); await page.keyboard.press('Alt+ArrowDown');
      let after = await rect('historyPane');
      check(parseFloat(after.x) > parseFloat(before.x) && parseFloat(after.y) > parseFloat(before.y), 'Alt arrows did not move float', { before, after });
      await unchanged(artwork, 'Alt arrows on floating tab');
      await frame('historyPane').locator('[data-collapse]').focus(); await page.keyboard.press('Alt+ArrowLeft');
      check(JSON.stringify(await rect('historyPane')) === JSON.stringify(after), 'Alt movement leaked to other floating controls');
      await unchanged(artwork, 'Alt+Left on floating Collapse button');
      await view('workspaceLockPanels'); before = await rect('historyPane');
      await tab('historyPane').focus(); await page.keyboard.press('Alt+ArrowRight');
      await drag(tab('historyPane'), { x: 850, y: 330 });
      check(JSON.stringify(await rect('historyPane')) === JSON.stringify(before), 'Lock allowed panel movement');
      await tab('historyPane').click({ button: 'right' });
      check(await page.locator('[data-dock-action="left"]').isDisabled(), 'Lock left placement still enabled');
    });
    await run('locked floating Alt Down cannot nudge selected artwork', async () => {
      await choose('historyPane', 'float'); await view('workspaceLockPanels');
      const before = await rect('historyPane'), artwork = await snapshot();
      await tab('historyPane').focus(); await page.keyboard.press('Alt+ArrowDown');
      check(JSON.stringify(await rect('historyPane')) === JSON.stringify(before), 'Locked Alt Down moved panel');
      await unchanged(artwork, 'Alt+Down on locked floating tab');
    });
    await run('Focus canvas and Reset recover all panels', async () => {
      await choose('historyPane', 'float'); await choose('propertiesPane', 'left');
      await view('workspaceFocusPanels');
      check(!await frame('historyPane').isVisible() && !await page.locator('.workspaceLeftDock').isVisible(), 'Focus mode leaves panels visible');
      await show('historyPane'); check(await frame('historyPane').isVisible(), 'Panels did not exit focus mode');
      await choose('propertiesPane', 'hide'); await view('workspaceReset');
      check(await place('propertiesPane') === 'home' && await place('historyPane') === 'home', 'Reset did not recover panels');
      check(await page.locator('.workspaceFloatingPanel').count() === 0, 'Reset left floating frames');
    });
    await run('repeated raise stays below tour and tour blocks panel drag', async () => {
      await choose('historyPane', 'float');
      const levels = [];
      for (let i = 0; i < 48; i++) {
        await tab('historyPane').click();
        levels.push(await frame('historyPane').evaluate(n => Number(getComputedStyle(n).zIndex)));
      }
      const tourZ = await page.locator('#editorTourLayer').evaluate(n => Number(getComputedStyle(n).zIndex));
      check(levels.every(value => value < tourZ), 'Repeated panel raise covers the guided tour', { levels, tourZ });
      check(levels.some((value, index) => index > 0 && value < levels[index - 1]), 'Repeated raise did not exercise z-index rollover', levels);
      const owner = await page.locator('#startEditorTour').evaluate(n => n.closest('.workspaceMenu').id);
      await page.locator(`[aria-controls="${owner}"]`).click(); await page.locator('#startEditorTour').click();
      await page.waitForFunction(() => editorTourState?.active);
      await settle();
      const before = await rect('historyPane');
      await drag(tab('historyPane'), { x: 850, y: 350 });
      check(JSON.stringify(await rect('historyPane')) === JSON.stringify(before), 'Tour allowed floating panel drag');
      await cleanDrag();
      await page.locator('#editorTourSkip').click();
      check(await page.evaluate(() => !editorTourState?.active), 'Tour did not close');
      measurements.push({ raiseCount: levels.length, minZ: Math.min(...levels), maxZ: Math.max(...levels), tourZ });
    });
  } else if (section === 'navigation') {
    for (const [name, selector, keys] of [
      ['home inspector tab', '.inspectorDock .dockTab[data-panel="propertiesPane"]', ['ArrowUp', 'ArrowDown', 'Alt+ArrowDown']],
      ['home layer options button', '#workspaceLayerPanelOptions', ['ArrowUp', 'ArrowDown', 'ArrowLeft']],
      ['text tool handle', '[data-tool-mode="text"]', ['ArrowUp', 'ArrowDown']],
      ['select tool handle', '[data-tool-mode="select"]', ['ArrowUp', 'ArrowDown']],
      ['right width separator', '#workspaceDockWidth', ['ArrowUp', 'ArrowDown']],
      ['layer dock splitter', '#dockSplitter', ['ArrowUp', 'ArrowDown']],
    ]) for (const key of keys) await run(`${name} ${key} navigation preserves selected artwork`, async () => {
      const before = await snapshot();
      const tool = await page.evaluate(() => activeToolMode);
      check(await page.evaluate(() => selectedVinylObjects().length) === 1, 'Navigation safety requires selected artwork');
      await page.locator(selector).focus();
      check(await page.locator(selector).evaluate(n => n === document.activeElement), 'Navigation target did not receive focus');
      await page.keyboard.press(key);
      await unchanged(before, `${key} on ${name}`);
      check(await page.evaluate(() => activeToolMode) === tool, 'Navigation changed active drawing tool');
    });
    await run('home tab Left Right navigation still activates panels', async () => {
      await tab('propertiesPane').focus(); await page.keyboard.press('ArrowRight');
      check(await page.locator('.inspectorDock .dockTab.active').getAttribute('data-panel') !== 'propertiesPane', 'Guard blocked tab navigation');
      await page.keyboard.press('ArrowLeft');
      check(await tab('propertiesPane').getAttribute('aria-selected') === 'true'
        && await tab('propertiesPane').evaluate(n => n === document.activeElement), 'Tab navigation did not return to Properties');
    });
    await run('right width separator Left Right still resizes', async () => {
      const handle = page.locator('#workspaceDockWidth');
      const before = Number(await handle.getAttribute('aria-valuenow'));
      await handle.focus(); await page.keyboard.press('ArrowRight');
      check(Number(await handle.getAttribute('aria-valuenow')) < before, 'Guard blocked right width resize');
      await page.keyboard.press('ArrowLeft');
      check(Number(await handle.getAttribute('aria-valuenow')) === before, 'Right width resize did not return to original width');
    });
  } else if (section === 'canvas-handoff') {
    baseline = null;
    await run('canvas click restores nudge after guarded panel navigation', async () => {
      await tab('propertiesPane').focus(); await page.keyboard.press('ArrowDown');
      check((await snapshot()).shapes === original, 'Panel navigation edited artwork before canvas handoff');
      const geometry = await h.geometry(page);
      check(await page.evaluate(point => document.elementFromPoint(point.x, point.y) === canvas.upperCanvasEl, geometry.grab),
        'Canvas handoff target is obscured');
      await page.mouse.click(geometry.grab.x, geometry.grab.y);
      await page.waitForFunction(() => selectedVinylObjects().length === 1);
      const selection = await page.evaluate(() => ({ id: objectToShape(selectedVinylObjects()[0]).editor_id,
        step: Number(document.getElementById('nudgeStep').value) || 1, focus: document.activeElement === canvas.upperCanvasEl }));
      check(selection.focus, 'Real canvas click did not restore keyboard focus');
      const before = (await snapshot()).shapes, expected = JSON.parse(before);
      const shape = expected.find(item => item.editor_id === selection.id);
      check(shape, 'Canvas click selected an unknown shape', selection);
      const xBefore = shape.data[0]; shape.data[0] += selection.step;
      await page.keyboard.press('ArrowRight'); await page.waitForFunction(() => !editorCommands.busy);
      check((await snapshot()).shapes === JSON.stringify(expected), 'Canvas nudge was blocked or changed more than selected X');
      await page.locator('#undoBtn').click(); await page.waitForFunction(() => !editorCommands.busy);
      check((await snapshot()).shapes === before && before === original, 'Canvas nudge did not undo to exact original artwork');
      measurements.push({ canvasHandoff: true, selection: selection.id, xBefore, xAfter: shape.data[0], exactUndo: true });
    });
  } else if (section === 'appearance') {
    await run('floating resize accessibility semantics', async () => {
      await choose('propertiesPane', 'float');
      const a11y = await frame('propertiesPane').locator('[data-resize]').evaluate(n => ({ role: n.getAttribute('role'),
        name: n.getAttribute('aria-label'), min: n.getAttribute('aria-valuemin'), max: n.getAttribute('aria-valuemax'),
        now: n.getAttribute('aria-valuenow'), text: n.getAttribute('aria-valuetext') }));
      measurements.push({ a11y });
      check(a11y.name && a11y.text && a11y.now !== null, 'Focusable separator has no numeric current value', a11y);
      check(a11y.min !== null && a11y.max !== null && Number(a11y.min) <= Number(a11y.now) && Number(a11y.now) <= Number(a11y.max),
        'Floating separator numeric bounds are missing or inconsistent', a11y);
      check(Number(a11y.now) === parseFloat((await rect('propertiesPane')).width), 'Floating separator value does not match width', a11y);
    });
    for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) await run(`theme ${theme} floating controls`, async () => {
      const available = await page.locator('#editorThemeSelect option').evaluateAll(nodes => nodes.map(n => n.value));
      check(available.includes(theme), 'Expected built-in theme missing', { theme, available });
      await page.locator('#workspaceViewMenu').click(); await page.locator('#editorThemeSelect').selectOption(theme); await closeMenus();
      await choose('propertiesPane', 'float'); await choose('historyPane', 'left');
      const result = await frame('propertiesPane').evaluate(n => {
        const s = getComputedStyle(n), probe = document.createElement('span'); n.append(probe); probe.style.color = 'var(--panel)';
        const panel = getComputedStyle(probe).color; probe.remove(); return { background: s.backgroundColor, text: s.color, panel };
      });
      check(result.background === result.panel && result.background !== result.text, 'Floating theme token mismatch', result);
      await page.screenshot({ path: path.join(output, `theme-${theme}.png`), timeout: 8000 });
    });
    for (const size of [{ width: 1100, height: 700 }, { width: 900, height: 640 }, { width: 760, height: 640 }, { width: 600, height: 500 }]) {
      await run(`narrow resize ${size.width}`, async () => {
        await page.setViewportSize({ width: 1600, height: 1000 });
        await choose('propertiesPane', 'left'); await choose('historyPane', 'float');
        await page.setViewportSize(size);
        await settle();
        const geometry = await page.evaluate(() => ({ width: innerWidth, height: innerHeight,
          scrollWidth: document.documentElement.scrollWidth, scrollHeight: document.documentElement.scrollHeight,
          boxes: ['.workspaceFloatingPanel', '.workspaceLeftDock', '.canvasStage'].map(selector => {
            const n = document.querySelector(selector), r = n.getBoundingClientRect();
            return { selector, x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
          }) }));
        measurements.push(geometry);
        check(geometry.scrollWidth <= size.width && geometry.scrollHeight <= size.height, 'Document overflow', geometry);
        for (const box of geometry.boxes) check(box.x >= 0 && box.y >= 0 && box.right <= size.width + 1 && box.bottom <= size.height + 1 && box.width > 0,
          'Panel or canvas escaped viewport', box);
        const close = frame('historyPane').getByRole('button', { name: 'Close panel', exact: true });
        await close.click(); await show('historyPane');
        check(await page.locator('#historyPane').isVisible(), 'Narrow Panels recovery failed');
        await page.screenshot({ path: path.join(output, `narrow-${size.width}.png`), timeout: 8000 });
      });
    }
    await page.setViewportSize({ width: 1600, height: 1000 });
  } else if (section === 'persistence') {
    await page.locator('#workspaceFileMenu').click(); await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill('Docking edge fixture'); await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
    baseline = null;
    const layouts = [null, { schema: 99, items: {} }, { schema: 1, items: 'invalid' },
      { schema: 1, locked: 'true', leftWidth: -99999, items: { propertiesPane: { place: 'bogus', rect: null }, historyPane: { place: 'floating', rect: { x: -1e12, y: 1e12, width: 1e12, height: -500 }, collapsed: 'true' }, layersPane: null } },
      { schema: 1, leftWidth: 'bad', items: { propertiesPane: { place: 'floating', rect: { x: 'x', y: {}, width: null, height: [] } }, historyPane: { place: 'left', order: 'bad' }, ghostPane: { place: 'floating' } } }];
    for (const [index, layout] of layouts.entries()) await run(`corrupted optional layout ${index}`, async () => {
      await page.evaluate(async value => { writeDockState({ panels: value }); await KfpsEditorPreferences.flush(); await flushPendingAutosave(); }, layout);
      await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready && window.KfpsDocking && document.querySelector('#workspacePanels'));
      await page.waitForFunction(() => vinylObjects().length === 12 && !recoveryRestoreDepth);
      check((await snapshot()).shapes === original, 'Corrupt optional layout changed saved artwork');
      const bad = await page.locator('.workspaceFloatingPanel').evaluateAll(nodes => nodes.map(n => n.getBoundingClientRect())
        .filter(r => !Number.isFinite(r.width) || r.width <= 0 || r.height <= 0 || r.x < 0 || r.y < 0 || r.right > innerWidth + 1 || r.bottom > innerHeight + 1).map(r => r.toJSON()));
      check(!bad.length, 'Corrupt rectangle escaped viewport', bad);
      await view('workspaceReset'); check(await page.locator('.workspaceFloatingPanel').count() === 0, 'Reset did not recover corrupt layout');
    });
    await run('Korean docking controls after saved preference reload', async () => {
      await page.evaluate(async () => { KfpsEditorPreferences.setItem('kloudyFabricLanguage', 'ko'); await KfpsEditorPreferences.flush(); });
      await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready && document.querySelector('#workspacePanels'));
      check(await page.evaluate(() => KfpsI18n.language) === 'ko', 'Korean preference not restored');
      await choose('historyPane', 'float');
      const localized = await page.evaluate(() => {
        const pairs = [
          ['#workspaceLockPanels', 'aria-label', 'Lock panel positions'], ['#workspaceFocusPanels', 'aria-label', 'Focus canvas'],
          ['#workspacePanels', null, 'Panels'], ['.workspaceLeftDock', 'aria-label', 'Left panels'],
          ['.workspaceLeftResize', 'aria-label', 'Resize left panels'], ['[data-dock-action="float"]', null, 'Float panel'],
          ['[data-dock-action="left"]', null, 'Dock left'], ['[data-dock-action="home"]', null, 'Dock right'],
          ['[data-dock-action="hide"]', null, 'Close panel'], ['.workspaceFloatingPanel [data-resize]', 'aria-label', 'Resize panel'],
          ['.workspaceFloatingPanel [data-collapse]', 'aria-label', 'Collapse or expand panel'],
          ['#workspaceLayerPanelOptions', 'aria-label', 'Panel options'],
        ];
        return pairs.map(([selector, attribute, key]) => { const n = document.querySelector(selector);
          return { selector, key, expected: KfpsI18n.t(key), actual: attribute ? n.getAttribute(attribute) : n.textContent.trim() }; });
      });
      measurements.push({ localized });
      for (const label of localized) check(label.expected === label.actual && /[\uac00-\ud7a3]/.test(label.actual), 'Untranslated Korean docking control', label);
      const tooltip = await tab('historyPane').getAttribute('data-workspace-tooltip');
      const expected = await page.evaluate(() => KfpsI18n.t('Drag to move this panel. Right-click for panel options. Alt+arrow keys move a floating panel.'));
      check(tooltip.includes(expected), 'Korean floating-tab tooltip missing');
      await page.setViewportSize({ width: 760, height: 640 });
      await page.screenshot({ path: path.join(output, 'korean-docking-760.png'), timeout: 8000 });
      await page.setViewportSize({ width: 1600, height: 1000 });
      await page.evaluate(async () => { KfpsEditorPreferences.setItem('kloudyFabricLanguage', 'en'); await KfpsEditorPreferences.flush(); });
    });
  } else throw Error('Unknown dockingEdgesSection: ' + section);

  if (baseline) await run('real redo and undo preserved after all docking actions', async () => {
    await page.locator('#redoBtn').click(); await page.waitForFunction(() => !editorCommands.busy);
    check((await snapshot()).shapes === duplicate, 'Docking broke exact redo');
    await page.locator('#undoBtn').click(); await page.waitForFunction(() => !editorCommands.busy);
    check((await snapshot()).shapes === original, 'Docking broke exact undo');
    // Undo/redo may advance command counters; assert the full pre-operation history separately above.
    baseline = null;
  });
  await closeMenus(); await page.evaluate(() => KfpsDocking.reset());
  if (options.dockingSaveForClose) {
    await page.locator('#workspaceFileMenu').click(); await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill(`Docking ${section} close fixture`);
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty && !editorCommands.busy);
    check((await snapshot()).shapes === original, 'Save for native close changed artwork');
    measurements.push({ savedForNativeClose: true });
  }
  await page.evaluate(async () => { await KfpsEditorPreferences.flush(); await flushPendingAutosave(); });
  const changedSources = Object.keys(sources).filter(name => hash(fs.readFileSync(path.join(webRoot, name))) !== sources[name]);
  if (changedSources.length) findings.push({ name: 'source identity', error: 'Sources changed during run: ' + changedSources.join(', ') });
  write();
  return { passed: !findings.length, section, cases, findings, measurements, sources,
    limits: 'Qt offscreen CDP input; window blur is synthetic; no physical input, native-focus or GPU-FPS claim.' };
}
