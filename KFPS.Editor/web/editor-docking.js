/* Panels move as original DOM nodes; the document and command owners stay shared. */
(function (root) {
  'use strict';
  const $ = id => document.getElementById(id);
  const t = (...args) => KfpsI18n.t(...args);
  const records = new Map();
  let workspace, home, left, layerHome, menu, menuOwner, initialized = false;
  let locked = false, focused = false, leftWidth = 320, drag = null, z = 40, suppressClick = false, layerFrame = null;
  const places = new Set(['home', 'left', 'floating', 'hidden']);
  const finite = (value, fallback) => Number.isFinite(value) ? value : fallback;
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  function control(label, symbol, action) {
    const node = document.createElement('button'); node.type = 'button';
    node.title = t(label); node.setAttribute('aria-label', t(label));
    node.append(KfpsWorkspace.icon(symbol)); node.addEventListener('click', action);
    return node;
  }
  function bounds(rect = {}) {
    const area = workspace.getBoundingClientRect();
    const width = clamp(finite(rect.width, 360), Math.min(280, area.width - 16), Math.max(80, area.width - 16));
    const height = clamp(finite(rect.height, 460), Math.min(180, area.height - 16), Math.max(80, area.height - 16));
    return { width, height, x: clamp(finite(rect.x, 100), 8, Math.max(8, area.width - width - 8)),
      y: clamp(finite(rect.y, 60), 8, Math.max(8, area.height - height - 8)) };
  }
  function save() {
    if (!initialized) return;
    const items = {};
    for (const [id, record] of records) items[id] = {
      place: record.place, rect: record.rect, collapsed: record.collapsed,
      active: record.tab.classList.contains('active'),
      order: record.tab.parentElement ? [...record.tab.parentElement.children].indexOf(record.tab) : record.index,
    };
    writeDockState({ panels: { schema: 1, locked, leftWidth, items } });
  }
  function groupTabs(group) { return [...group.querySelectorAll(':scope > .dockTabs > .dockTab')]; }
  function select(record) {
    const group = record.pane.parentElement;
    groupTabs(group).forEach(tab => {
      const active = tab === record.tab;
      tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    [...group.children].filter(node => node.classList.contains('dockPane')).forEach(pane => {
      pane.hidden = pane !== record.pane; pane.classList.toggle('active', pane === record.pane);
    });
    record.collapsed = false;
    record.frame?.classList.remove('panelMinimized');
    record.frame?.querySelector('[data-collapse]')?.setAttribute('aria-expanded', 'true');
    raise(record);
  }
  function activate(id) {
    if (!initialized || !records.has(id)) return false;
    const record = records.get(id);
    if (record.place === 'hidden') move(id, 'home', null, false);
    if (focused) focusCanvas(false);
    if (record.place === 'home') {
      setDockVisible(true);
      if (id === 'layersPane') setLayersCollapsed(false);
    }
    select(record); refresh(); save(); return true;
  }
  function repair(group) {
    if (!group?.isConnected) return;
    const tabs = groupTabs(group);
    if (tabs.length && !tabs.some(tab => tab.classList.contains('active'))) select(records.get(tabs[0].dataset.panel));
  }
  function raise(record) {
    if (!record.frame) return;
    if (++z > 100) {
      z = 40;
      for (const item of records.values()) if (item.frame) item.frame.style.zIndex = String(++z);
    }
    record.frame.style.zIndex = String(++z);
  }
  function position(record) {
    record.rect = bounds(record.rect);
    const rect = record.rect;
    Object.assign(record.frame.style, { left: `${rect.x}px`, top: `${rect.y}px`, width: `${rect.width}px`, height: `${rect.height}px` });
    record.frame.classList.toggle('panelMinimized', record.collapsed);
    const resize = record.frame.querySelector('[data-resize]');
    const maxWidth = Math.max(80, workspace.getBoundingClientRect().width - 16);
    resize.setAttribute('aria-valuemin', String(Math.min(280, maxWidth)));
    resize.setAttribute('aria-valuemax', String(maxWidth));
    resize.setAttribute('aria-valuenow', String(Math.round(rect.width)));
    resize.setAttribute('aria-valuetext', `${Math.round(rect.width)} x ${Math.round(rect.height)}`);
  }
  function makeFloat(record) {
    const frame = document.createElement('section'); frame.className = 'dockGroup workspaceFloatingPanel';
    frame.setAttribute('aria-label', record.label); frame.dataset.panelFrame = record.id;
    const bar = document.createElement('div'); bar.className = 'dockTabs'; bar.setAttribute('role', 'tablist');
    const actions = document.createElement('div'); actions.className = 'workspacePanelActions';
    actions.append(control('Panel options', 'Ellipsis', event => openMenu(record, event.currentTarget)),
      control('Collapse or expand panel', 'ChevronDown', () => {
        record.collapsed = !record.collapsed; position(record); save();
        actions.querySelector('[data-collapse]').setAttribute('aria-expanded', String(!record.collapsed));
      }), control('Close panel', 'X', () => { move(record.id, 'hidden'); $('workspaceViewMenu').focus(); }));
    actions.children[1].dataset.collapse = ''; actions.children[1].setAttribute('aria-expanded', String(!record.collapsed));
    bar.append(actions); frame.append(bar);
    const resize = document.createElement('div'); resize.className = 'workspacePanelResize'; resize.dataset.resize = '';
    resize.tabIndex = 0; resize.setAttribute('role', 'separator'); resize.setAttribute('aria-label', t('Resize panel'));
    resize.setAttribute('aria-orientation', 'vertical');
    resize.title = t('Resize panel'); resize.append(KfpsWorkspace.icon('Maximize'));
    resize.addEventListener('pointerdown', event => startDrag(event, record, 'resize'));
    resize.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation();
      if (event.key === 'Home') record.rect = { ...record.rect, width: 360, height: 460 };
      else record.rect = { ...record.rect, width: record.rect.width + ({ ArrowLeft: -16, ArrowRight: 16 }[event.key] || 0),
        height: record.rect.height + ({ ArrowUp: -16, ArrowDown: 16 }[event.key] || 0) };
      position(record); refresh(); save();
    });
    guardPanelNavigation(resize);
    frame.append(resize); frame.addEventListener('pointerdown', () => raise(record));
    frame.addEventListener('focusin', () => raise(record));
    workspace.append(frame); record.frame = frame; bindTabKeys(bar); position(record);
    return frame;
  }
  function move(id, place, rect = null, persist = true, before = null) {
    const record = records.get(id); if (!record || !places.has(place)) return;
    const previous = record.pane.parentElement;
    record.tab.remove(); record.pane.remove(); record.frame?.remove(); record.frame = null;
    record.place = place; record.collapsed = false;
    if (rect) record.rect = bounds(rect);
    record.tab.hidden = record.id === 'layersPane' && place === 'home';
    record.pane.dataset.dockPlace = place;
    if (place === 'hidden') {
      record.pane.hidden = true;
      $('workspacePanelParking').append(record.tab, record.pane);
    } else {
      const group = place === 'home' ? (id === 'layersPane' ? layerHome : home) : place === 'left' ? left : makeFloat(record);
      if (!(id === 'layersPane' && place === 'home')) {
        const bar = group.querySelector(':scope > .dockTabs');
        const next = records.get(before)?.tab;
        bar.insertBefore(record.tab, next?.parentElement === bar ? next : bar.querySelector('.workspacePanelActions'));
      } else $('workspacePanelParking').append(record.tab);
      group.append(record.pane); select(record);
    }
    repair(previous); refresh(); if (persist) save();
  }
  function refresh() {
    const hasLeft = groupTabs(left).length > 0;
    workspace.classList.toggle('hasLeftDock', hasLeft);
    workspace.classList.toggle('workspaceFocusMode', focused);
    left.hidden = !hasLeft;
    workspace.style.setProperty('--workspace-left-width', `${leftWidth}px`);
    const right = document.querySelector('.rightDock');
    const hasLayers = $('layersPane').parentElement === layerHome;
    const hasInspector = groupTabs(home).length > 0;
    right.classList.toggle('layersUndocked', !hasLayers);
    right.classList.toggle('inspectorEmpty', !hasInspector);
    workspace.classList.toggle('rightDockEmpty', !hasLayers && !hasInspector);
    $('collapseLayersDock').hidden = !hasLayers;
    $('workspaceLockPanels').setAttribute('aria-pressed', String(locked));
    $('workspaceFocusPanels').setAttribute('aria-pressed', String(focused));
    workspace.classList.toggle('panelPositionsLocked', locked);
    scheduleCanvasResize();
    if (layerFrame === null) layerFrame = requestAnimationFrame(() => {
      layerFrame = null;
      if ($('layersPane').getClientRects().length) renderVirtualLayerWindow(true);
    });
  }
  function focusCanvas(value) { focused = value; refresh(); }
  function reset() {
    if (!initialized) return;
    cancelDrag(); locked = false; focused = false; leftWidth = 320;
    for (const record of records.values()) move(record.id, 'home', null, false);
    select(records.get('propertiesPane')); setDockVisible(true); setLayersCollapsed(false);
    refresh(); save();
  }
  function openMenu(record, anchor, point) {
    menuOwner = record;
    menu.querySelector('[data-panel-title]').textContent = record.label;
    for (const button of menu.querySelectorAll('[data-dock-action]')) {
      button.disabled = locked && ['home', 'left', 'float'].includes(button.dataset.dockAction);
    }
    if (!menu.matches(':popover-open')) menu.showPopover();
    const r = anchor.getBoundingClientRect();
    menu.style.left = `${clamp(point?.x ?? r.left, 8, Math.max(8, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${clamp(point?.y ?? r.bottom, 8, Math.max(8, innerHeight - menu.offsetHeight - 8))}px`;
    menu.__trigger = anchor; menu.querySelector('button:not(:disabled)')?.focus();
  }
  function bindTabKeys(bar) {
    bar.addEventListener('keydown', event => {
      const tabs = groupTabs(bar.parentElement), index = tabs.indexOf(event.target);
      if (index < 0 || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
        : (index + (event.key === 'ArrowLeft' ? -1 : 1) + tabs.length) % tabs.length;
      activate(tabs[next].dataset.panel); tabs[next].focus();
    });
    guardPanelNavigation(bar);
  }
  function guardPanelNavigation(node) {
    // Unhandled panel navigation, including locked Alt moves, cannot edit artwork.
    for (const type of ['keydown', 'keyup']) node.addEventListener(type, event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation();
    });
  }
  function bindHandle(handle, record) {
    handle.classList.add('workspacePanelHandle'); handle.dataset.dockPanel = record.id;
    handle.title = [handle.title || handle.dataset.workspaceTooltip, t('Drag to move this panel. Right-click for panel options. Alt+arrow keys move a floating panel.')].filter(Boolean).join(' ');
    handle.addEventListener('pointerdown', event => startDrag(event, record, 'move'));
    handle.addEventListener('contextmenu', event => { event.preventDefault(); openMenu(record, handle, { x: event.clientX, y: event.clientY }); });
    handle.addEventListener('keydown', event => {
      if (handle === record.tab && record.place === 'floating' && event.altKey && !locked
        && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
        event.preventDefault(); event.stopPropagation();
        record.rect = { ...record.rect, x: record.rect.x + ({ ArrowLeft: -16, ArrowRight: 16 }[event.key] || 0),
          y: record.rect.y + ({ ArrowUp: -16, ArrowDown: 16 }[event.key] || 0) };
        position(record); save(); return;
      }
      if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
        event.preventDefault(); event.stopPropagation(); openMenu(record, handle);
      }
    });
  }
  function startDrag(event, record, mode) {
    if (event.button !== 0 || drag || (locked && mode === 'move') || document.querySelector('dialog[open]')
      || document.body.classList.contains('editorTourActive')) return;
    event.preventDefault();
    event.currentTarget.focus({ preventScroll: true });
    const handleRect = event.currentTarget.getBoundingClientRect();
    drag = { record, mode, handle: event.currentTarget, capture: event.currentTarget, pointer: event.pointerId,
      x: event.clientX, y: event.clientY, rect: { ...record.rect }, started: false,
      place: record.place, before: record.tab.nextElementSibling?.dataset.panel, focused,
      collapsed: record.collapsed, active: [...records.values()].filter(item =>
        ['home', 'left'].includes(item.place) && item.tab.classList.contains('active')).map(item => item.id),
      offsetX: clamp(event.clientX - handleRect.left, 16, record.rect.width - 32),
      offsetY: clamp(event.clientY - handleRect.top, 4, 30) };
    drag.capture.setPointerCapture(event.pointerId);
  }
  function dropTarget(x, y) {
    const target = document.elementFromPoint(x, y);
    const bar = target?.closest('.dockTabs');
    if (bar && (bar.parentElement === home || bar.parentElement === left)) {
      return { place: bar.parentElement === home ? 'home' : 'left', before: target.closest('.dockTab')?.dataset.panel };
    }
    const area = workspace.getBoundingClientRect();
    if (y < area.top || y > area.bottom) return null;
    if (x >= area.left && x <= area.left + 90) return { place: 'left' };
    if (x <= area.right && x >= area.right - 90) return { place: 'home' };
    return null;
  }
  function moveDrag(event) {
    if (!drag || drag.pointer !== event.pointerId) return;
    const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    if (!drag.started && Math.hypot(dx, dy) < 6) return;
    if (!drag.started) {
      drag.started = true; suppressClick = true;
      // The original handle can be reparented. Keep capture on the stable workspace.
      drag.capture = workspace; workspace.setPointerCapture(drag.pointer);
      workspace.classList.add('panelDragging');
      if (drag.mode === 'move') {
        if (focused) { focused = false; refresh(); }
        if (drag.place !== 'floating') {
          const area = workspace.getBoundingClientRect();
          move(drag.record.id, 'floating', { ...drag.rect,
            x: event.clientX - area.left - drag.offsetX, y: event.clientY - area.top - drag.offsetY }, false);
        }
        drag.record.frame.classList.add('workspacePanelMoving');
        raise(drag.record);
        drag.handle.focus({ preventScroll: true });
      }
    }
    event.preventDefault();
    if (drag.mode === 'resize') {
      drag.record.rect = { ...drag.rect, width: drag.rect.width + dx, height: drag.rect.height + dy };
      position(drag.record);
    } else {
      drag.target = dropTarget(event.clientX, event.clientY);
      const area = workspace.getBoundingClientRect();
      drag.nextRect = bounds(drag.place === 'floating'
        ? { ...drag.rect, x: drag.rect.x + dx, y: drag.rect.y + dy }
        : { ...drag.rect, x: event.clientX - area.left - drag.offsetX, y: event.clientY - area.top - drag.offsetY });
      drag.record.rect = drag.nextRect; position(drag.record);
      $('workspaceDockHintLeft').classList.toggle('active', drag.target?.place === 'left');
      $('workspaceDockHintRight').classList.toggle('active', drag.target?.place === 'home');
    }
  }
  function finishDrag(cancel) {
    if (!drag) return;
    const current = drag; drag = null;
    current.record.frame?.classList.remove('workspacePanelMoving'); workspace.classList.remove('panelDragging');
    if (current.capture.hasPointerCapture(current.pointer)) current.capture.releasePointerCapture(current.pointer);
    if (current.started) {
      if (cancel) {
        focused = current.focused;
        if (current.mode === 'move' && current.place !== 'floating') {
          move(current.record.id, current.place, current.rect, false, current.before);
          for (const id of current.active) select(records.get(id));
        }
        current.record.rect = current.rect; current.record.collapsed = current.collapsed;
        if (current.record.frame) position(current.record);
      }
      if (!cancel && current.mode === 'move') {
        if (current.target) move(current.record.id, current.target.place, current.nextRect, false, current.target.before);
      }
      const handle = current.handle.isConnected && current.handle.getClientRects().length ? current.handle
        : current.record.id === 'layersPane' && current.record.place === 'home' ? $('layersPane').querySelector('h2')
        : current.record.tab.getClientRects().length ? current.record.tab : $('workspaceViewMenu');
      handle.focus({ preventScroll: true });
      refresh(); if (!cancel) save();
      setTimeout(() => { suppressClick = false; }, 0);
    }
  }
  function cancelDrag() { finishDrag(true); }
  function init() {
    if (initialized) return;
    workspace = document.querySelector('.workspace'); home = document.querySelector('.inspectorDock');
    layerHome = document.querySelector('.layersDock');
    guardPanelNavigation(home.querySelector('.dockTabs'));
    guardPanelNavigation(document.querySelector('.toolRail'));
    guardPanelNavigation($('workspaceDockWidth'));
    guardPanelNavigation($('dockSplitter'));
    const parked = document.createElement('div'); parked.id = 'workspacePanelParking'; parked.hidden = true; workspace.append(parked);
    left = document.createElement('aside'); left.className = 'dockGroup workspaceLeftDock'; left.setAttribute('aria-label', t('Left panels'));
    left.innerHTML = '<div class="dockTabs" role="tablist"></div>';
    workspace.insertBefore(left, document.querySelector('.canvasStage')); bindTabKeys(left.firstChild);
    const leftResize = document.createElement('div'); leftResize.className = 'workspaceLeftResize'; leftResize.tabIndex = 0;
    leftResize.setAttribute('role', 'separator'); leftResize.setAttribute('aria-orientation', 'vertical');
    leftResize.setAttribute('aria-label', t('Resize left panels')); leftResize.title = t('Resize left panels');
    leftResize.setAttribute('aria-valuemin', '280'); leftResize.setAttribute('aria-valuemax', '480');
    left.append(leftResize);
    let resizeStart = null;
    const setLeftWidth = value => { leftWidth = clamp(value, 280, 480); leftResize.setAttribute('aria-valuenow', String(leftWidth)); refresh(); };
    leftResize.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault(); resizeStart = { x: event.clientX, width: leftWidth, pointer: event.pointerId }; leftResize.setPointerCapture(event.pointerId);
    });
    leftResize.addEventListener('pointermove', event => { if (resizeStart?.pointer === event.pointerId) setLeftWidth(resizeStart.width + event.clientX - resizeStart.x); });
    const endLeftResize = cancel => {
      if (!resizeStart) return;
      const old = resizeStart; resizeStart = null;
      if (cancel) setLeftWidth(old.width); else save();
      if (leftResize.hasPointerCapture(old.pointer)) leftResize.releasePointerCapture(old.pointer);
    };
    leftResize.addEventListener('pointerup', () => endLeftResize(false));
    leftResize.addEventListener('pointercancel', () => endLeftResize(true));
    leftResize.addEventListener('lostpointercapture', () => endLeftResize(true));
    leftResize.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation(); setLeftWidth(event.key === 'Home' ? 320 : leftWidth + (event.key === 'ArrowRight' ? 16 : -16)); save();
    });
    guardPanelNavigation(leftResize);
    const tabs = [...home.querySelectorAll('.dockTab')];
    const layersTab = document.createElement('button'); layersTab.className = 'dockTab'; layersTab.dataset.panel = 'layersPane';
    layersTab.textContent = t('Layers'); layersTab.setAttribute('role', 'tab'); layersTab.setAttribute('aria-controls', 'layersPane');
    layersTab.hidden = true; parked.append(layersTab); tabs.push(layersTab);
    layersTab.addEventListener('click', () => activateDockPanel('layersPane'));
    tabs.forEach((tab, index) => {
      const record = { id: tab.dataset.panel, tab, pane: $(tab.dataset.panel), label: tab.textContent,
        index, place: 'home', rect: bounds({ x: 100 + index * 16, y: 50 + index * 12 }), collapsed: false };
      records.set(record.id, record); bindHandle(tab, record);
    });
    const layerTitle = $('layersPane').querySelector('h2'); layerTitle.tabIndex = 0;
    bindHandle(layerTitle, records.get('layersPane'));
    guardPanelNavigation(layerTitle);
    const layerOptions = control('Panel options', 'Ellipsis', event => openMenu(records.get('layersPane'), event.currentTarget));
    guardPanelNavigation(layerOptions);
    layerOptions.id = 'workspaceLayerPanelOptions'; $('layersPane').querySelector('.panelHeaderActions').prepend(layerOptions);
    const toolPanels = { select: 'propertiesPane', shapeLibrary: 'shapeLibraryPane', text: 'textPane', pixelArt: 'pixelArtPane',
      guides: 'guidesPane', overlay: 'overlayPane', source: 'overlayPane', dropper: 'propertiesPane' };
    document.querySelectorAll('.toolButton[data-tool-mode]').forEach(tool => {
      const record = records.get(toolPanels[tool.dataset.toolMode]); if (record) bindHandle(tool, record);
    });
    menu = document.createElement('div'); menu.id = 'workspacePanelMenu'; menu.className = 'workspaceMenu';
    menu.setAttribute('popover', 'auto'); menu.setAttribute('role', 'menu');
    const title = document.createElement('strong'); title.dataset.panelTitle = ''; menu.append(title);
    for (const [action, label] of [['float', 'Float panel'], ['left', 'Dock left'], ['home', 'Dock right'], ['hide', 'Close panel']]) {
      const button = document.createElement('button'); button.textContent = t(label); button.dataset.dockAction = action; button.setAttribute('role', 'menuitem');
      button.addEventListener('click', () => {
        const record = menuOwner; menu.hidePopover();
        move(record.id, action === 'float' ? 'floating' : action === 'hide' ? 'hidden' : action);
        if (action !== 'hide') activateDockPanel(record.id);
        (record.tab.hidden || action === 'hide' ? $('workspaceViewMenu') : record.tab).focus();
      }); menu.append(button);
    }
    document.body.append(menu);
    const view = $('workspaceViewCommands');
    const panels = document.createElement('button'); panels.id = 'workspacePanels'; panels.textContent = t('Panels');
    const list = document.createElement('div'); list.id = 'workspacePanelsMenu'; document.body.append(list);
    for (const record of records.values()) {
      const button = document.createElement('button'); button.textContent = record.label; button.dataset.showPanel = record.id;
      button.addEventListener('click', () => activateDockPanel(record.id)); list.append(button);
    }
    KfpsWorkspace.attachMenu(panels, list); view.append(panels);
    const lock = control('Lock panel positions', 'Lock', () => { locked = !locked; refresh(); save(); });
    lock.id = 'workspaceLockPanels'; lock.append(document.createTextNode(t('Lock panel positions')));
    const focus = control('Focus canvas', 'PanelRightClose', () => focusCanvas(!focused));
    focus.id = 'workspaceFocusPanels'; focus.append(document.createTextNode(t('Focus canvas'))); view.append(lock, focus);
    for (const [id, label] of [['Left', 'Dock left'], ['Right', 'Dock right']]) {
      const hint = document.createElement('div'); hint.id = `workspaceDockHint${id}`; hint.className = `workspaceDockHint dockHint${id}`;
      hint.textContent = t(label); workspace.append(hint);
    }
    const stored = readDockState().panels;
    const state = stored?.schema === 1 && stored.items && typeof stored.items === 'object' ? stored : {};
    locked = state.locked === true; leftWidth = clamp(finite(state.leftWidth, 320), 280, 480);
    const ordered = [...records.values()].sort((a, b) => finite(state.items?.[a.id]?.order, a.index) - finite(state.items?.[b.id]?.order, b.index));
    for (const record of ordered) {
      const item = state.items?.[record.id]; if (!item || !places.has(item.place)) continue;
      move(record.id, item.place, bounds(item.rect || {}), false);
      record.collapsed = item.collapsed === true;
      if (record.frame) position(record);
    }
    for (const record of records.values()) {
      if (state.items?.[record.id]?.active && ['home', 'left'].includes(record.place)) select(record);
    }
    initialized = true; leftResize.setAttribute('aria-valuenow', String(leftWidth)); refresh();
    document.addEventListener('pointermove', moveDrag);
    document.addEventListener('pointerup', event => { if (drag?.pointer === event.pointerId) finishDrag(false); });
    document.addEventListener('pointercancel', cancelDrag);
    document.addEventListener('lostpointercapture', event => {
      if (drag?.pointer === event.pointerId && event.target === drag.capture) cancelDrag();
    });
    document.addEventListener('click', event => { if (suppressClick) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && (drag || resizeStart)) {
        event.preventDefault(); event.stopImmediatePropagation(); cancelDrag(); endLeftResize(true);
      } else if (drag?.started) {
        event.preventDefault(); event.stopImmediatePropagation();
      }
    }, true);
    window.addEventListener('blur', () => { cancelDrag(); endLeftResize(true); });
    window.addEventListener('resize', () => { cancelDrag(); for (const record of records.values()) if (record.frame) position(record); refresh(); });
  }
  root.KfpsDocking = Object.freeze({ init, activate, reset });
})(window);
