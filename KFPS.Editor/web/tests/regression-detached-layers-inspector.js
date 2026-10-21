async (page, testOptions = {}) => {
  const fs = require('node:fs');
  const path = require('node:path');
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const check = (ok, message) => { if (!ok) throw Error(message); };
  // Both background page harnesses supply output and process.json. Use fresh
  // run/profile subdirectories here, never an installed or personal profile.
  const root = path.resolve(__dirname, '../../..');
  const runRoot = path.join(root, 'runtime/test-runs/detached-layers-20261021');
  const within = value => {
    const resolved = fs.existsSync(value) ? fs.realpathSync(value) : path.resolve(value);
    const relative = path.relative(fs.realpathSync(runRoot), resolved);
    return !path.isAbsolute(relative) && relative !== '..' && !relative.startsWith('..' + path.sep);
  };
  check(within(output), 'Run output must be under ' + runRoot);
  const processInfo = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
  check(fs.realpathSync(processInfo.appRoot) === fs.realpathSync(root), 'Only the DIRTY app is allowed');
  check(within(processInfo.profile), 'Test profile must be under ' + runRoot);
  check(processInfo.exportRoot && within(processInfo.exportRoot), 'Pass a private --export-root under ' + runRoot);
  if (testOptions.browserHost) {
    check(JSON.parse(fs.readFileSync(path.join(output, 'host.json'), 'utf8')).background === true,
      'Chrome harness must run in background');
  } else check(processInfo.windowPolicy === 'background-no-activation', 'Native harness must run in background');

  const cases = [], measurements = [];
  const report = () => fs.writeFileSync(path.join(output, 'detached-layers-inspector.json'),
    JSON.stringify({ cases, measurements, profile: processInfo.profile,
      host: testOptions.browserHost ? 'chrome' : 'native' }, null, 2));
  const settle = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const tab = id => page.locator(`.inspectorDock .dockTab[data-panel="${id}"]`);
  const place = () => page.locator('#layersPane').getAttribute('data-dock-place');
  const closeMenus = async () => {
    for (let i = 0; i < 3 && await page.locator('.workspaceMenu:popover-open').count(); i++) await page.keyboard.press('Escape');
  };
  const command = async id => {
    await closeMenus();
    const menu = await page.locator('#' + id).evaluate(node => node.closest('.workspaceMenu')?.id);
    if (menu) await page.locator(`[aria-controls="${menu}"]`).click();
    await page.locator('#' + id).click();
  };
  const moveLayers = async action => {
    await closeMenus();
    const handle = await place() === 'home' ? page.locator('#layersPane h2')
      : page.locator('.dockTab[data-panel="layersPane"]');
    await handle.click({ button: 'right' });
    await page.locator(`#workspacePanelMenu [data-dock-action="${action}"]`).click();
    check(await place() === (action === 'float' ? 'floating' : action), 'Layers did not move: ' + action);
    await settle();
    if (action === 'float') {
      // Floating panels may intentionally cover the inspector at small sizes.
      // Move this fixture aside through its supported keyboard handle first.
      const frame = await page.locator('[data-panel-frame="layersPane"]').boundingBox();
      const inspector = await page.locator('.rightDock').boundingBox();
      const steps = Math.max(0, Math.ceil((frame.x + frame.width - inspector.x + 8) / 16));
      check(steps < 64, 'Unexpected floating fixture geometry');
      await page.locator('.dockTab[data-panel="layersPane"]').focus();
      for (let i = 0; i < steps; i++) await page.keyboard.press('Alt+ArrowLeft');
      await settle();
    }
  };

  async function inspect(label, paneId = 'propertiesPane', controlId = 'xInput', requireEnabled = true) {
    await settle();
    await page.mouse.move(10, 10);
    const geometry = await page.evaluate(({ paneId, controlId }) => {
      const dock = document.querySelector('.rightDock > .inspectorDock');
      const pane = document.getElementById(paneId), control = document.getElementById(controlId);
      const rect = node => {
        const r = node.getBoundingClientRect();
        return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, height: r.height };
      };
      // Raw child boxes and isVisible alone can pass when a zero-height grid
      // ancestor clips all content. Measure the actually exposed intersection.
      const visible = node => {
        const box = rect(node);
        let left = Math.max(0, box.x), top = Math.max(0, box.y);
        let right = Math.min(innerWidth, box.right), bottom = Math.min(innerHeight, box.bottom);
        for (let parent = node.parentElement; parent; parent = parent.parentElement) {
          const r = rect(parent), s = getComputedStyle(parent);
          if (parent === dock || /hidden|clip|auto|scroll/.test(s.overflowX)) { left = Math.max(left, r.x); right = Math.min(right, r.right); }
          if (parent === dock || /hidden|clip|auto|scroll/.test(s.overflowY)) { top = Math.max(top, r.y); bottom = Math.min(bottom, r.bottom); }
        }
        return { width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
      };
      const c = rect(control), point = { x: c.x + c.width / 2, y: c.y + c.height / 2 };
      const hit = document.elementFromPoint(point.x, point.y);
      return { viewport: { width: innerWidth, height: innerHeight }, dock: rect(dock), pane: rect(pane),
        paneVisible: visible(pane), control: c, controlVisible: visible(control), point,
        active: !pane.hidden && pane.classList.contains('active') && pane.parentElement === dock,
        selectedTab: dock.querySelector('.dockTab[aria-selected="true"]')?.dataset.panel,
        enabled: !control.disabled, hit: hit === control || control.contains(hit),
        hitTarget: hit?.id || hit?.tagName, rightClasses: dock.parentElement.className,
        gridRows: getComputedStyle(dock.parentElement).gridTemplateRows };
    }, { paneId, controlId });
    measurements.push({ label, paneId, controlId, ...geometry });
    report();
    // Capture before asserting so a red run preserves the blank inspector.
    await page.screenshot({ path: path.join(output, label + '.png'), timeout: 8000 });
    check(geometry.active && geometry.selectedTab === paneId, label + ': inspector pane is not active');
    check(geometry.dock.height >= 160 && geometry.paneVisible.height >= 80 && geometry.paneVisible.width >= 200,
      label + ': inspector content collapsed/clipped: ' + JSON.stringify(geometry));
    check(geometry.controlVisible.width >= 40 && geometry.controlVisible.height >= 22 && (!requireEnabled || geometry.enabled) && geometry.hit,
      label + ': inspector control is not substantially visible/clickable: ' + JSON.stringify(geometry));
    return geometry.point;
  }

  const snapshot = () => page.evaluate(() => JSON.stringify(snapshotShapes()));
  const exact = expected => page.waitForFunction(expected => !editorCommands.busy && JSON.stringify(snapshotShapes()) === expected,
    expected, { timeout: 10000 });
  const save = async () => {
    await command('saveProject');
    await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty() && !editorCommands.busy);
    await page.evaluate(async () => { await KfpsEditorPreferences.flush(); await flushPendingAutosave(); });
  };
  async function editAndUndo(label) {
    const before = await snapshot(), edited = JSON.parse(before);
    edited.find(shape => shape.editor_id === 'inspector-target').data[0] = 125;
    const point = await inspect(label);
    await page.mouse.click(point.x, point.y);
    check(await page.locator('#xInput').evaluate(node => document.activeElement === node), label + ': X did not receive pointer focus');
    await page.keyboard.press('Control+A'); await page.keyboard.type('125'); await page.keyboard.press('Enter');
    await exact(JSON.stringify(edited));
    await tab('historyPane').click();
    const undo = await inspect(label + '-history', 'historyPane', 'historyUndo');
    await page.mouse.click(undo.x, undo.y);
    await exact(before);
    await tab('propertiesPane').click();
    await inspect(label + '-properties-restored');
    check(Number(await page.locator('#xInput').inputValue()) === 10, label + ': undo did not refresh X');
  }
  async function reloadLayout(label) {
    await save();
    const before = await page.evaluate(() => ({ shapes: JSON.stringify(snapshotShapes()),
      place: document.getElementById('layersPane').dataset.dockPlace,
      collapsed: document.querySelector('.rightDock').classList.contains('layersCollapsed') }));
    await page.reload();
    await page.waitForFunction(() => window.KfpsDesktop?.ready && window.KfpsDocking);
    await page.waitForFunction(expected => document.querySelector('#autosaveRecoveryDialog')?.open
      || (!recoveryRestoreDepth && JSON.stringify(snapshotShapes()) === expected), before.shapes);
    if (await page.locator('#autosaveRecoveryDialog').isVisible()) await page.locator('#recoverAutosave').click();
    await exact(before.shapes);
    await page.waitForFunction(() => !recoveryRestoreDepth && !document.querySelector('#autosaveRecoveryDialog').open);
    check(await place() === before.place, label + ': Layers placement did not survive reload');
    check(await page.locator('.rightDock').evaluate(node => node.classList.contains('layersCollapsed')) === before.collapsed,
      label + ': collapsed state did not survive reload');
    // Do not activate a tab before measuring: that could mask a restore defect.
    await inspect(label + '-reloaded', 'propertiesPane', 'xInput', false);
    // Opening a project deliberately clears selection; reselect through Layers
    // before expecting numeric inputs to be enabled, without switching tabs.
    if (before.collapsed) await page.locator('#collapseLayersDock').click();
    await h.select(page, 'Inspector target');
    if (before.collapsed) await page.locator('#collapseLayersDock').click();
    const point = await inspect(label + '-reselected');
    await page.mouse.click(point.x, point.y);
    check(await page.locator('#xInput').evaluate(node => document.activeElement === node), label + ': reloaded X is not clickable');
  }

  page.setDefaultTimeout(10000);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await command('workspaceReset');
  const fixture = path.join(output, 'inspector-input.json');
  fs.writeFileSync(fixture, JSON.stringify({ shapes: [
    { type: 1048678, color: [40, 150, 170, 255], data: [10, 0, .4, .4, 0, 0, 0], editor_id: 'inspector-target', shape_name: 'Inspector target' },
    { type: 1048678, color: [210, 80, 130, 255], data: [-180, 80, .3, .3, 0, 0, 0], editor_id: 'inspector-other', shape_name: 'Untouched layer' },
  ] }));
  await h.fileInput(page, '#jsonInput', fixture);
  await page.waitForFunction(() => vinylObjects().length === 2 && !recoveryRestoreDepth);
  await h.select(page, 'Inspector target');
  await command('saveProjectAs');
  await page.locator('#textPromptInput').fill('Detached Layers inspector regression');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty());
  const baseline = await snapshot();

  for (const size of [{ width: 1600, height: 1000 }, { width: 900, height: 700 }, { width: 760, height: 700 }]) {
    for (const mode of ['floating', 'collapsed', 'left']) {
      const label = `${size.width}-${mode}`;
      try {
        await page.setViewportSize(size);
        await command('workspaceReset');
        await h.select(page, 'Inspector target');
        check(await snapshot() === baseline, label + ': fixture changed before case');
        if (mode === 'collapsed') await page.locator('#collapseLayersDock').click();
        else await moveLayers(mode === 'floating' ? 'float' : 'left');
        if (mode === 'collapsed') check(await page.locator('.rightDock').evaluate(node => node.classList.contains('layersCollapsed')),
          label + ': Layers did not collapse');
        await editAndUndo(label);
        // One saved reload per placement, at normal size, keeps this focused.
        if (size.width === 1600) await reloadLayout(label);
        if (mode === 'floating') {
          await page.locator('[data-panel-frame="layersPane"] [data-collapse]').click();
          const frame = page.locator('[data-panel-frame="layersPane"]');
          check(await frame.locator('[data-collapse]').getAttribute('aria-expanded') === 'false'
            && (await frame.boundingBox()).height <= 36, label + ': floating Layers did not minimize');
          await inspect(label + '-minimized');
        } else if (mode === 'collapsed') {
          await moveLayers('float');
          await inspect(label + '-collapsed-and-detached');
        }
        await moveLayers('home');
        check(await page.locator('.layersDock > #layersPane').count() === 1, label + ': Layers did not return right');
        await inspect(label + '-returned-right');
        check(await snapshot() === baseline, label + ': docking changed artwork');
        cases.push({ label, passed: true });
      } catch (error) {
        cases.push({ label, passed: false, error: String(error.stack || error) });
        await page.screenshot({ path: path.join(output, label + '-failure.png'), timeout: 8000 }).catch(() => {});
        report();
        throw error;
      }
      report();
    }
  }
  await page.setViewportSize({ width: 1600, height: 1000 });
  await command('workspaceReset');
  await save();
  report();
  return { passed: cases.every(item => item.passed), cases, report: 'detached-layers-inspector.json',
    limits: 'Background CDP input and saved-page reloads; no native-focus or fresh-process restart claim.' };
}
