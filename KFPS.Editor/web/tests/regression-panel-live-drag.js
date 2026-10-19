async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const check = (ok, message, detail) => { if (!ok) throw Error(message + (detail ? ': ' + JSON.stringify(detail) : '')); };
  const write = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, null, 2));
  const report = { cases: [], limitations: 'Real CDP mouse input in the production host; blur and pointercancel are injected. No physical input or GPU performance claim.' };
  const tab = id => `.dockTab[data-panel="${id}"]`;
  const frame = id => `[data-panel-frame="${id}"]`;
  const art = () => page.evaluate(() => ({ shapes: JSON.stringify(snapshotShapes()), history: JSON.stringify({
    entries: editorHistory.entries, index: editorHistory.index, floor: editorHistory.floor, sequence: editorHistory.sequence,
  }) }));
  // Reset and reparent schedule layout work. Require consecutive stable rendered geometry.
  const settle = () => page.evaluate(async () => {
    let previous, stable = 0;
    for (let i = 0; i < 30; i++) {
      await new Promise(resolve => requestAnimationFrame(resolve));
      const current = JSON.stringify([...document.querySelectorAll('.workspace,.dockTabs,.dockPane,.workspaceFloatingPanel')]
        .map(node => { const r = node.getBoundingClientRect(); return [node.id, r.x, r.y, r.width, r.height]; }));
      stable = current === previous ? stable + 1 : 0; previous = current;
      if (stable >= 2) return;
    }
    throw Error('Panel layout did not settle within 30 frames');
  });
  const layout = () => page.evaluate(() => ({
    saved: editorSettings.getItem(EDITOR_DOCK_KEY),
    focusMode: document.querySelector('.workspace').classList.contains('workspaceFocusMode'),
    orders: [...document.querySelectorAll('.dockGroup > .dockTabs')].map(bar => ({
      group: bar.parentElement.dataset.panelFrame || bar.parentElement.className,
      tabs: [...bar.querySelectorAll(':scope > .dockTab')].map(node => node.dataset.panel),
    })).sort((a, b) => a.group.localeCompare(b.group)),
    panes: [...document.querySelectorAll('.dockPane')].map(pane => {
      const tab = document.querySelector(`.dockTab[data-panel="${pane.id}"]`), owner = pane.parentElement;
      const r = pane.getBoundingClientRect();
      return { id: pane.id, place: pane.dataset.dockPlace, hidden: pane.hidden, active: tab.classList.contains('active'),
        tabHidden: tab.hidden, collapsed: owner.classList.contains('panelMinimized'),
        rect: [r.x, r.y, r.width, r.height],
        float: owner.dataset.panelFrame ? [owner.style.left, owner.style.top, owner.style.width, owner.style.height] : null };
    }).sort((a, b) => a.id.localeCompare(b.id)),
  }));
  const point = async selector => {
    const value = await page.evaluate(selector => {
      const node = document.querySelector(selector); if (!node) return { missing: selector };
      const r = node.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2;
      const hit = document.elementFromPoint(x, y);
      return { x, y, width: r.width, height: r.height, hit: hit?.id || hit?.className,
        valid: r.width > 0 && r.height > 0 && x > 0 && y > 0 && x < innerWidth && y < innerHeight && node.contains(hit) };
    }, selector);
    check(value.valid, 'Start/drop point does not hit the actual rendered handle', { selector, ...value }); return value;
  };
  const choose = async (id, action) => {
    await settle();
    await page.locator(tab(id)).click({ button: 'right' });
    await page.locator(`[data-dock-action="${action}"]`).click(); await settle();
  };
  const clean = () => page.evaluate(() => !document.querySelector('.workspacePanelGhost,.panelDragging,.workspacePanelMoving'));
  let caseBefore, saved, held = false;
  const probe = async (id, control) => {
    await settle(); await page.evaluate(() => KfpsEditorPreferences.flush());
    caseBefore = await layout(); saved = caseBefore.saved;
    await page.evaluate(({ id, control }) => {
      const p = window.__panelLiveProbe;
      p.id = id; p.pane = document.getElementById(id); p.tab = document.querySelector(`.dockTab[data-panel="${id}"]`);
      p.control = document.querySelector(control); p.pointer = null; p.samples = [];
      p.rowKeys = [...p.pane.querySelectorAll('.layerRow')].map(node => node.dataset.layerListKey);
      p.tool = activeToolMode;
    }, { id, control });
  };
  const begin = async selector => {
    await settle(); const from = await point(selector);
    await page.mouse.move(from.x, from.y);
    // Recheck after hover: a top-layer tooltip must not intercept the intended pointerdown.
    await point(selector); await page.mouse.down(); held = true; return from;
  };
  const sample = async (label, location, resize = false) => {
    await page.mouse.move(location.x, location.y); await settle();
    const state = await page.evaluate(({ label, location }) => {
      const p = window.__panelLiveProbe, pane = document.getElementById(p.id), frame = pane.closest('.workspaceFloatingPanel');
      const rect = node => { const r = node?.getBoundingClientRect(); return r ? { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom } : null; };
      const visible = node => !!node && node.getClientRects().length > 0 && getComputedStyle(node).visibility === 'visible'
        && getComputedStyle(node).display !== 'none' && Number(getComputedStyle(node).opacity) > 0;
      const ids = [...document.querySelectorAll('[id]')].map(node => node.id), hit = document.elementFromPoint(location.x, location.y);
      const controlRect = rect(p.control), paneRect = rect(pane);
      const rowKeys = [...pane.querySelectorAll('.layerRow')].map(node => node.dataset.layerListKey);
      const result = { label, location, place: pane.dataset.dockPlace, pane: paneRect, frame: rect(frame), control: controlRect,
        samePane: pane === p.pane, sameTab: document.querySelector(`.dockTab[data-panel="${p.id}"]`) === p.tab,
        sameControl: p.control === document.getElementById(p.control?.id), visible: visible(pane) && visible(p.control),
        controlInPane: controlRect && paneRect && controlRect.x >= paneRect.x - 1 && controlRect.right <= paneRect.right + 1
          && controlRect.y >= paneRect.y - 1 && controlRect.bottom <= paneRect.bottom + 1,
        duplicateIds: ids.filter((id, index) => ids.indexOf(id) !== index), ghost: !!document.querySelector('.workspacePanelGhost'),
        capture: document.querySelector('.workspace').hasPointerCapture(p.pointer), dragging: document.querySelector('.workspace').classList.contains('panelDragging'),
        pointer: p.pointer, hit: hit?.id || hit?.className, hitLiftedFrame: !!frame?.contains(hit),
        leftHint: document.getElementById('workspaceDockHintLeft').classList.contains('active'),
        rightHint: document.getElementById('workspaceDockHintRight').classList.contains('active'),
        saved: editorSettings.getItem(EDITOR_DOCK_KEY), rowKeys, retainedRows: p.rowKeys.filter(key => rowKeys.includes(key)),
        tool: activeToolMode, workspace: rect(document.querySelector('.workspace')),
        colors: frame ? { background: getComputedStyle(frame).backgroundColor, text: getComputedStyle(frame).color } : null };
      p.samples.push(result); return result;
    }, { label, location });
    check(state.samePane && state.sameTab && state.sameControl && state.visible && state.controlInPane,
      'Original pane and control are not visibly present during drag', state);
    check(state.place === 'floating' && state.frame && state.dragging && state.capture,
      'Gesture did not cross threshold with stable workspace capture', state);
    check(!state.ghost && !state.duplicateIds.length, 'Drag cloned IDs or left a label ghost', state);
    check(state.saved === saved, 'In-progress gesture persisted a draft layout');
    if (!resize) check(!state.hitLiftedFrame, 'Lifted pane intercepted underlying dock hit testing', state);
    if (report.cases.at(-1)?.name === 'live contents and underlying left/right dock targets'
      && ['intermediate-1', 'intermediate-2'].includes(label)) {
      const name = `panel-live-${label}.png`;
      report.liveScreenshots ||= [];
      if (!report.liveScreenshots.includes(name)) {
        await page.screenshot({ path: path.join(output, name) });
        report.liveScreenshots.push(name);
      }
    }
    return state;
  };
  const twoMoves = async (first, second, resize = false) => {
    const a = await sample('intermediate-1', first, resize), b = await sample('intermediate-2', second, resize);
    if (resize) check(b.frame.width > a.frame.width + 4 && b.frame.height > a.frame.height + 4, 'Resize did not update twice before release', { a, b });
    else {
      const dx = b.pane.x - a.pane.x, dy = b.pane.y - a.pane.y;
      check(Math.hypot(dx, dy) > 8, 'Live pane did not follow the second pointer position', { a, b });
      check(Math.abs(b.control.x - a.control.x - dx) < 2 && Math.abs(b.control.y - a.control.y - dy) < 2,
        'Original control did not move with the pane', { a, b });
    }
    return [a, b];
  };
  const end = async () => { await page.mouse.up(); held = false; await settle(); check(await clean(), 'Drag UI remained after release'); };
  const cancel = async (kind, last) => {
    if (kind === 'Escape') await page.keyboard.press('Escape');
    else if (kind === 'blur') await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    else if (kind === 'pointercancel') await page.evaluate(() => document.querySelector('.workspace').dispatchEvent(new PointerEvent('pointercancel', {
      pointerId: window.__panelLiveProbe.pointer, pointerType: 'mouse', bubbles: true,
    })));
    else {
      await page.evaluate(() => document.querySelector('.workspace').releasePointerCapture(window.__panelLiveProbe.pointer));
      await page.mouse.move(last.x + 1, last.y + 1);
    }
    await settle();
    const after = await layout();
    check(await clean(), `${kind} did not cancel before mouseup`);
    check(JSON.stringify(after) === JSON.stringify(caseBefore), `${kind} did not restore place/order/active/collapsed/rect/persistence`, { before: caseBefore, after });
    await end();
    check(JSON.stringify(await layout()) === JSON.stringify(caseBefore), `${kind} mouseup committed a cancelled draft`);
  };
  const run = async (name, action) => {
    if (options.panelLiveCases && !options.panelLiveCases.some(part => name.includes(part))) return;
    console.log('panel-live: ' + name);
    const entry = { name, passed: false }, started = Date.now(); report.cases.push(entry);
    await page.evaluate(name => { const p = window.__panelLiveProbe; p.events = []; p.samples = []; p.name = name; }, name);
    try {
      await page.setViewportSize({ width: 1600, height: 1000 });
      await page.evaluate(() => KfpsDocking.reset()); await settle();
      const before = await art(); await action();
      check(await clean(), 'Case left a live gesture'); check(JSON.stringify(await art()) === JSON.stringify(before), 'Panel workflow changed exact artwork/history');
      entry.passed = true;
    } catch (error) {
      entry.error = String(error.stack || error);
      write('panel-live-drag-failure.json', { name, error: entry.error, before: caseBefore, after: await layout(),
        trace: await page.evaluate(() => { const p = window.__panelLiveProbe; return { events: p.events, samples: p.samples }; }) });
      throw error;
    } finally {
      if (held) { await page.mouse.up(); held = false; }
      entry.ms = Date.now() - started;
      entry.evidence = await page.evaluate(() => { const p = window.__panelLiveProbe; return { events: p.events, samples: p.samples }; });
      write('panel-live-drag.json', report);
    }
  };
  page.setDefaultTimeout(8000);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.evaluate(() => {
    const p = window.__panelLiveProbe = { events: [], samples: [], listeners: [] };
    const add = (owner, type) => {
      const listener = event => {
        if (type === 'pointerdown') p.pointer = event.pointerId;
        const pane = document.getElementById(p.id), r = pane?.getBoundingClientRect();
        p.events.push({ type, at: performance.now(), target: event.target?.id || event.target?.className || 'window',
          pointer: event.pointerId, x: event.clientX, y: event.clientY, buttons: event.buttons, trusted: event.isTrusted,
          focus: document.activeElement?.id || document.activeElement?.dataset.panel || document.activeElement?.className,
          place: pane?.dataset.dockPlace, pane: r ? [r.x, r.y, r.width, r.height] : null });
        if (p.events.length > 256) p.events.shift();
      };
      owner.addEventListener(type, listener, true); p.listeners.push({ owner, type, listener });
    };
    ['pointerdown', 'pointerup', 'pointercancel', 'gotpointercapture', 'lostpointercapture'].forEach(type => add(document, type));
    ['blur', 'resize'].forEach(type => add(window, type));
  });
  try {
    const fixture = path.join(output, 'panel-live-12-shapes.json');
    fs.writeFileSync(fixture, JSON.stringify({ shapes: Array.from({ length: 12 }, (_, i) => ({
      type: [1048677, 1048678, 1048679][i % 3], color: [50 + i * 12, 160, 190, 255],
      data: [-200 + i % 4 * 130, 150 - Math.floor(i / 4) * 130, .35, .4, i * 15, 0, 0],
      editor_id: `panel-live-${i}`, shape_name: `Panel shape ${i}`,
    })) }));
    await h.fileInput(page, '#jsonInput', fixture);
    await page.waitForFunction(() => vinylObjects().length === 12 && !recoveryRestoreDepth);
    await h.select(page, 'Panel shape 5'); await page.locator('#layerSearch').fill('');
    await page.locator('#quickDuplicateLayer').click(); await page.waitForFunction(() => vinylObjects().length === 13 && !editorCommands.busy);
    await page.locator('#undoBtn').click(); await page.waitForFunction(() => vinylObjects().length === 12 && !editorCommands.busy);
    await h.select(page, 'Panel shape 5'); await page.locator('#layerSearch').fill(''); await settle();

    await run('live contents and underlying left/right dock targets', async () => {
      for (const side of ['left', 'home']) {
        await probe('propertiesPane', '#xInput'); await begin(tab('propertiesPane'));
        await twoMoves({ x: 610, y: 220 }, { x: 710, y: 280 });
        const area = await page.locator('.workspace').evaluate(node => node.getBoundingClientRect().toJSON());
        const state = await sample('underlying-dock-target', { x: side === 'left' ? area.left + 60 : area.right - 30, y: area.top + 200 });
        check(side === 'left' ? state.leftHint : state.rightHint, 'Underlying dock target was not detected');
        await end(); check(await page.locator('#propertiesPane').getAttribute('data-dock-place') === side, 'Dock commit differs from highlighted target');
      }
    });
    await run('neighbor tooltip then live tab reorder', async () => {
      const before = await page.locator('.inspectorDock .dockTab').evaluateAll(nodes => nodes.map(node => node.dataset.panel));
      await probe('historyPane', '#historyUndo');
      const hover = await point(tab('overlayPane')); await page.mouse.move(hover.x, hover.y);
      await page.waitForFunction(() => document.querySelector('.dockTab[data-panel="overlayPane"]').getAttribute('aria-describedby')?.includes('workspaceTooltip')
        && document.getElementById('workspaceTooltip').matches(':popover-open'));
      await begin(tab('historyPane'));
      await twoMoves({ x: 610, y: 220 }, { x: 710, y: 280 });
      const target = await point(tab(before[0])); const state = await sample('underlying-tab-target', target);
      check(state.rightHint, 'Reorder did not find the underlying home tab strip'); await end();
      const after = await page.locator('.inspectorDock .dockTab').evaluateAll(nodes => nodes.map(node => node.dataset.panel));
      check(JSON.stringify(after) === JSON.stringify(['historyPane', ...before.filter(id => id !== 'historyPane')]), 'Tab insertion order changed unexpectedly', { before, after });
    });
    for (const kind of ['Escape', 'blur', 'pointercancel', 'lostcapture']) await run(`live move cancellation ${kind}`, async () => {
      if (kind === 'blur') await choose('propertiesPane', 'left');
      if (kind === 'pointercancel') await choose('propertiesPane', 'float');
      if (kind === 'lostcapture') {
        await choose('historyPane', 'float'); await page.locator(`${frame('historyPane')} [data-collapse]`).click();
        await choose('propertiesPane', 'float');
      }
      if (kind === 'Escape') await page.locator(tab('historyPane')).click();
      await probe('propertiesPane', '#xInput'); await begin(tab('propertiesPane'));
      const last = { x: 710, y: 280 }; await twoMoves({ x: 610, y: 220 }, last); await cancel(kind, last);
    });
    await run('live resize commit and Escape rollback', async () => {
      await choose('propertiesPane', 'float');
      for (const rollback of [false, true]) {
        await probe('propertiesPane', '#xInput'); const from = await begin(`${frame('propertiesPane')} [data-resize]`);
        const last = { x: from.x + 60, y: from.y + 40 };
        await twoMoves({ x: from.x + 25, y: from.y + 20 }, last, true);
        if (rollback) await cancel('Escape', last);
        else { await end(); check((await layout()).saved !== saved, 'Committed resize was not persisted'); }
      }
    });
    await run('tool-rail original text controls without tool activation', async () => {
      await page.locator('[data-tool-mode="select"]').click();
      const tool = await page.evaluate(() => activeToolMode);
      await page.locator('#workspaceViewMenu').click(); await page.locator('#workspaceFocusPanels').click();
      check((await layout()).focusMode, 'Focus-mode fixture was not activated');
      for (const rollback of [true, false]) {
        await probe('textPane', '#textVinylInput'); await begin('[data-tool-mode="text"]');
        const last = { x: 710, y: 280 }, samples = await twoMoves({ x: 610, y: 220 }, last);
        check(!(await layout()).focusMode, 'Moving pane stayed hidden in focus mode');
        await page.keyboard.press('ArrowRight'); await page.keyboard.press('Control+z');
        check(samples.every(sample => sample.tool === tool) && await page.evaluate(() => activeToolMode) === tool, 'Tool-rail drag activated a drawing tool');
        if (rollback) await cancel('Escape', last); else await end();
      }
      check(await page.locator('#textPane').getAttribute('data-dock-place') === 'floating', 'Tool-rail drag did not commit floating pane');
    });
    await run('layers header keeps original controls and mounted rows', async () => {
      await probe('layersPane', '#layerSearch'); await begin('#layersPane h2');
      const samples = await twoMoves({ x: 610, y: 220 }, { x: 710, y: 280 });
      check(samples.every(sample => sample.rowKeys.length > 0 && sample.retainedRows.length > 0), 'Layers content disappeared during lift', samples);
      await end(); check(await page.locator('#layersPane').getAttribute('data-dock-place') === 'floating', 'Layers header did not detach');
      await probe('layersPane', '#layerSearch'); await begin(tab('layersPane'));
      await twoMoves({ x: 610, y: 220 }, { x: 710, y: 280 });
      const area = await page.locator('.workspace').evaluate(node => node.getBoundingClientRect().toJSON());
      await sample('layers-reattach', { x: area.right - 30, y: area.top + 200 }); await end();
      check(await page.locator('#layersPane').getAttribute('data-dock-place') === 'home', 'Layers did not reattach');
      check(await page.evaluate(() => document.activeElement === document.querySelector('#layersPane h2')), 'Reattached Layers did not focus its visible header');
    });
    for (const [theme, width, height] of [['pastel', 1600, 1000], ['dark', 1280, 800], ['blackout', 760, 640], ['whiteout', 760, 640]]) {
      await run(`theme containment ${theme} ${width}x${height}`, async () => {
        await page.setViewportSize({ width, height }); await settle();
        await page.locator('#workspaceViewMenu').click(); await page.locator('#editorThemeSelect').selectOption(theme); await page.keyboard.press('Escape');
        await choose('propertiesPane', 'float'); await probe('propertiesPane', '#xInput');
        const direction = await page.evaluate(() => {
          const r = document.querySelector('[data-panel-frame="propertiesPane"]').getBoundingClientRect();
          const area = document.querySelector('.workspace').getBoundingClientRect();
          return { x: area.right - r.right > 80 ? 1 : -1, y: area.bottom - r.bottom > 45 ? 1 : -1 };
        });
        const from = await begin(tab('propertiesPane'));
        const samples = await twoMoves({ x: from.x + 30 * direction.x, y: from.y + 15 * direction.y },
          { x: from.x + 70 * direction.x, y: from.y + 35 * direction.y });
        for (const s of samples) check(s.frame.x >= s.workspace.x && s.frame.y >= s.workspace.y && s.frame.right <= s.workspace.right
          && s.frame.bottom <= s.workspace.bottom && s.colors.background !== 'rgba(0, 0, 0, 0)' && s.colors.background !== s.colors.text,
        'Live pane escaped viewport or lost theme surface/text contrast', s);
        await end();
      });
    }
    check(report.cases.length > 0, 'No panelLiveCases matched');
    await page.evaluate(() => KfpsDocking.reset()); await settle();
    if (options.panelLiveSave !== false) {
      const source = fs.readFileSync(path.join(__dirname, 'regression-host-editing-matrix.js'), 'utf8');
      fs.writeFileSync(path.join(output, 'test-inputs', 'panel-live-save-only.js'), source);
      report.saved = await eval(`(${source})`)(page, { saveOnly: true });
    }
    report.passed = true; write('panel-live-drag.json', report); return report;
  } finally {
    if (held) await page.mouse.up();
    await page.evaluate(() => {
      const p = window.__panelLiveProbe;
      for (const { owner, type, listener } of p.listeners) owner.removeEventListener(type, listener, true);
      delete window.__panelLiveProbe;
    });
  }
}
