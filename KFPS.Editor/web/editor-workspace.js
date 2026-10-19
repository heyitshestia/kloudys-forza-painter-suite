/* Presentation adapter: moves existing controls without duplicating editing state. */
(function (root) {
  'use strict';
  const $ = id => document.getElementById(id);
  const t = (...args) => KfpsI18n.t(...args);
  const iconButtons = new Map();
  let initialized = false;
  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    for (const [key, value] of Object.entries({ viewBox: '0 0 24 24', width: 18, height: 18,
      fill: 'none', stroke: 'currentColor', 'stroke-width': 1.8, 'stroke-linecap': 'round',
      'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false' })) svg.setAttribute(key, value);
    svg.classList.add('workspaceIcon');
    for (const [tag, attrs] of root.KfpsIconNodes[name] || []) {
      const element = document.createElementNS(svg.namespaceURI, tag);
      for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
      svg.append(element);
    }
    return svg;
  }
  function button(id, label, symbol, action) {
    const node = document.createElement('button');
    node.type = 'button'; node.id = id; node.textContent = t(label); node.title = t(label);
    if (action) node.addEventListener('click', action);
    if (symbol) decorate(node, symbol);
    return node;
  }
  function decorate(node, symbol, iconOnly = false) {
    if (!node) return;
    if (!node.querySelector(':scope > .workspaceIcon')) {
      const label = node.textContent.trim();
      const caption = document.createElement('span'); caption.className = 'buttonCaption';
      caption.textContent = label;
      node.replaceChildren(icon(symbol), caption);
      node.setAttribute('aria-label', label || node.title);
    }
    node.classList.add('workspaceButton');
    node.classList.toggle('workspaceIconOnly', iconOnly);
    iconButtons.set(node, { symbol, iconOnly });
  }
  function positionMenu(trigger, menu) {
    const rect = trigger.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(rect.bottom + 4, innerHeight - menu.offsetHeight - 8))}px`;
  }
  function attachMenu(trigger, menu) {
    trigger.removeAttribute('popovertarget');
    trigger.setAttribute('aria-haspopup', 'menu'); trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', menu.id);
    menu.setAttribute('popover', 'auto'); menu.setAttribute('role', 'menu');
    menu.classList.add('workspaceMenu'); menu.__trigger = trigger;
    menu.querySelectorAll('button').forEach(item => item.setAttribute('role', 'menuitem'));
    trigger.addEventListener('click', () => {
      if (menu.matches(':popover-open')) menu.hidePopover();
      else { menu.showPopover(); positionMenu(trigger, menu); }
    });
    trigger.addEventListener('keydown', event => {
      if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation();
      if (!menu.matches(':popover-open')) menu.showPopover();
      positionMenu(trigger, menu);
      const items = menuItems(menu); items[event.key === 'ArrowUp' ? items.length - 1 : 0]?.focus();
    });
    menu.addEventListener('toggle', () => {
      const open = menu.matches(':popover-open'); trigger.setAttribute('aria-expanded', String(open));
      if (open) positionMenu(trigger, menu);
    });
    menu.addEventListener('click', event => {
      if (event.target.closest('button') && menu.matches(':popover-open')) menu.hidePopover();
    });
  }
  function menuItems(menu) {
    return [...menu.querySelectorAll('button:not(:disabled), select, input:not(:disabled)')]
      .filter(node => node.getClientRects().length);
  }
  function restoreMenuFocus(menu) {
    let trigger = menu.__trigger;
    while (trigger && !trigger.getClientRects().length) trigger = trigger.closest('.workspaceMenu')?.__trigger;
    trigger?.focus();
  }
  function setupMenus() {
    const bar = document.querySelector('.appMenus');
    const groups = [...bar.querySelectorAll('.menuGroup')];
    const actions = document.createElement('div'); actions.className = 'workspaceDocumentActions';
    ['undoBtn', 'redoBtn', 'loadProject', 'saveProject', 'exportJson'].forEach(id => actions.append($(id)));
    bar.after(actions);
    const symbols = { undoBtn: 'Undo2', redoBtn: 'Redo2', loadProject: 'FolderOpen', saveProject: 'Save', exportJson: 'Download' };
    Object.entries(symbols).forEach(([id, symbol]) => decorate($(id), symbol, ['undoBtn', 'redoBtn'].includes(id)));
    const labels = ['File', 'Edit', 'View', 'Help'];
    groups.forEach((group, i) => {
      group.querySelector(':scope > span')?.remove();
      group.id = `workspace${labels[i]}Commands`;
      const trigger = button(`workspace${labels[i]}Menu`, labels[i]);
      trigger.className = 'workspaceMenuTrigger';
      group.before(trigger); attachMenu(trigger, group);
    });
    const view = groups[2];
    const reset = button('workspaceReset', 'Reset workspace', 'LayoutPanelLeft', resetLayout);
    view.append(reset, document.querySelector('.themePicker'));
    const menuIcons = { newCanvas: 'FilePlus2', openJsonBrowser: 'FolderOpen', saveProjectAs: 'Save',
      copyLayer: 'Copy', pasteLayer: 'ClipboardPaste', duplicateLayer: 'Copy', deleteLayer: 'Trash2',
      fitView: 'Scan', resetView: 'Maximize', fitSelected: 'Focus', toggleRightDock: 'PanelRight',
      startEditorTour: 'MousePointer2', helpBtn: 'CircleHelp', shortcutsBtn: 'Keyboard' };
    Object.entries(menuIcons).forEach(([id, name]) => decorate($(id), name));
    // Menus own their navigation; arrows must never nudge artwork underneath.
    document.addEventListener('keydown', event => {
      const menu = document.activeElement?.closest('.workspaceMenu:popover-open')
        || [...document.querySelectorAll('.workspaceMenu:popover-open')].at(-1);
      if (!menu || event.isComposing || event.keyCode === 229) return;
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopImmediatePropagation(); menu.hidePopover(); restoreMenuFocus(menu); return;
      }
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(event.target.tagName)) return;
      event.stopImmediatePropagation();
      const items = menuItems(menu), index = items.indexOf(document.activeElement);
      if (['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
          : index < 0 ? (event.key === 'ArrowUp' ? items.length - 1 : 0)
          : (index + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
        items[next]?.focus();
      } else if (event.key === 'Tab') {
        menu.hidePopover(); restoreMenuFocus(menu);
      }
    }, true);
    window.addEventListener('resize', () => document.querySelectorAll('.workspaceMenu:popover-open')
      .forEach(menu => positionMenu(menu.__trigger, menu)));
  }
  function setupTools() {
    const symbols = { select: 'MousePointer2', shapeLibrary: 'Shapes', text: 'Type', pixelArt: 'Grid2X2',
      dropper: 'Pipette', guides: 'Ruler', overlay: 'Image', source: 'Move' };
    document.querySelectorAll('.toolButton').forEach(node => {
      const caption = node.querySelector('span')?.textContent || node.textContent;
      const hint = document.createElement('span'); hint.className = 'toolCaption'; hint.textContent = caption;
      node.replaceChildren(icon(symbols[node.dataset.toolMode] || 'Blend'), hint);
      node.setAttribute('aria-label', node.title);
    });
    const quick = { quickDuplicateLayer: 'Copy', quickDeleteLayer: 'Trash2', quickGroupSelected: 'Group', quickFitSelected: 'Focus' };
    Object.entries(quick).forEach(([id, name]) => decorate($(id), name, true));
    const overlap = $('overlapCycle').closest('label');
    overlap.classList.add('workspaceOverlap');
    const text = [...overlap.childNodes].find(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim());
    if (text) text.textContent = ` ${t('Cycle overlaps')}`;
    document.querySelector('.contextBar').append(overlap);
    const ready = document.querySelector('.contextBar .statusChip');
    if (ready) document.querySelector('.bottomStatus').append(ready);
    document.querySelector('.canvasStage').setAttribute('aria-label', t('Artwork canvas'));
    const empty = $('emptyCanvasHint');
    empty.querySelector('h2').textContent = t('Untitled vinyl');
    empty.querySelector('p').remove();
  }
  function setupLayers() {
    const menu = $('layerGroupActions');
    ['renameSelectedLayer', 'renameSelectedGroup', 'hideSelectedGroup', 'lockSelectedGroup', 'ungroupSelected', 'changeSelectedShape']
      .forEach(id => menu.append($(id)));
    attachMenu($('groupActions'), menu);
    const icons = { bringFront: 'ArrowUpToLine', bringForward: 'ArrowUp', sendBackward: 'ArrowDown', sendBack: 'ArrowDownToLine',
      selectionLockToggle: 'Lock', groupSelected: 'Group', groupActions: 'Ellipsis', collapseLayersDock: 'ChevronUp' };
    Object.entries(icons).forEach(([id, name]) => decorate($(id), name, true));
    $('groupActions').title = t('Layer and group actions');
    $('groupActions').setAttribute('aria-label', t('Layer and group actions'));
    $('layerInfo').setAttribute('aria-live', 'polite');
    $('layerSearch').setAttribute('aria-label', t('Filter layers by name, type, or number'));
    const search = document.createElement('div'); search.className = 'workspaceLayerSearch';
    $('layerSearch').before(search); search.append(icon('Search'), $('layerSearch'));
  }
  function setupProperties() {
    const pane = $('propertiesPane');
    const transform = $('xInput').closest('.propertySection');
    transform.classList.add('workspaceTransform');
    pane.querySelector('.selectedCard').after(transform);
    const proportion = document.createElement('span'); proportion.className = 'workspaceTransformMode';
    proportion.title = t('Corner handles preserve proportions; side handles resize one axis. Shift-corner skews. Numeric scales are independent.');
    proportion.tabIndex = 0;
    proportion.append(icon('Link'), document.createTextNode(t('Proportional corners')));
    transform.querySelector('h3').after(proportion);
    const flips = { flipHorizontal: 'FlipHorizontal2', flipVertical: 'FlipVertical2', rotateLeft: 'RotateCcw', rotateRight: 'RotateCw' };
    Object.entries(flips).forEach(([id, name]) => decorate($(id), name, true));
    // Keep advanced capabilities available while reducing the initial scroll burden.
    [...pane.querySelectorAll(':scope > .propertySection')].slice(2).forEach(section => {
      const heading = section.querySelector('h3'); if (!heading) return;
      const details = document.createElement('details'); details.className = 'workspaceDisclosure';
      const summary = document.createElement('summary'); summary.textContent = heading.textContent;
      section.before(details); details.append(summary, section); heading.hidden = true;
    });
    const tablist = document.querySelector('.dockTabs');
    tablist.setAttribute('aria-label', t('Inspector panels'));
    tablist.querySelectorAll('.dockTab').forEach(tab => {
      tab.setAttribute('role', 'tab'); tab.setAttribute('aria-controls', tab.dataset.panel);
      tab.addEventListener('click', () => writeDockState({ panel: tab.dataset.panel }));
    });
    tablist.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const tabs = [...tablist.querySelectorAll('.dockTab')], index = tabs.indexOf(event.target);
      if (index < 0) return;
      event.preventDefault(); event.stopPropagation();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1
        : (index + (event.key === 'ArrowLeft' ? -1 : 1) + tabs.length) % tabs.length;
      tabs[next].click(); tabs[next].focus();
    });
  }
  function setWidth(value, persist = false) {
    const width = Math.max(320, Math.min(580, Number(value) || 384));
    document.querySelector('.editorShell').style.setProperty('--workspace-dock-width', `${width}px`);
    const splitter = $('workspaceDockWidth'); splitter?.setAttribute('aria-valuenow', String(Math.round(width)));
    if (persist) writeDockState({ width });
    scheduleCanvasResize();
  }
  function resetLayout() {
    root.KfpsDocking?.reset();
    setWidth(384, true);
    writeDockState({ hidden: false, layersCollapsed: false, layerPercent: 48, panel: 'propertiesPane' });
    restoreDockState(); activateDockPanel('propertiesPane');
    $('propertiesPane').scrollTop = 0;
    document.querySelectorAll('.workspaceDisclosure').forEach(node => { node.open = false; });
    scheduleCanvasResize();
  }
  function setupDock() {
    const dock = document.querySelector('.rightDock');
    const splitter = document.createElement('div'); splitter.id = 'workspaceDockWidth'; splitter.tabIndex = 0;
    splitter.setAttribute('role', 'separator'); splitter.setAttribute('aria-orientation', 'vertical');
    splitter.setAttribute('aria-label', t('Resize inspector width')); splitter.title = t('Resize inspector width');
    splitter.setAttribute('aria-valuemin', '320'); splitter.setAttribute('aria-valuemax', '580');
    dock.append(splitter);
    const state = readDockState();
    setWidth(state.width);
    if (!Number.isFinite(Number(state.layerPercent))) {
      document.querySelector('.editorShell').style.setProperty('--editor-layer-height', '48%');
    }
    if (state.panel && document.querySelector(`.dockTab[data-panel="${CSS.escape(String(state.panel))}"]`)) {
      activateDockPanel(state.panel); setDockVisible(!state.hidden);
    }
    let drag = null;
    splitter.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault(); drag = { id: event.pointerId, x: event.clientX, width: dock.getBoundingClientRect().width };
      splitter.setPointerCapture(event.pointerId); splitter.classList.add('dragging');
    });
    splitter.addEventListener('pointermove', event => {
      if (drag?.id === event.pointerId) setWidth(Math.min(innerWidth - 372, drag.width + drag.x - event.clientX));
    });
    function finish(cancel) {
      if (!drag) return;
      const current = drag; drag = null;
      setWidth(cancel ? current.width : Number(splitter.getAttribute('aria-valuenow')), !cancel);
      splitter.classList.remove('dragging');
      if (splitter.hasPointerCapture(current.id)) splitter.releasePointerCapture(current.id);
    }
    splitter.addEventListener('pointerup', () => finish(false));
    splitter.addEventListener('pointercancel', () => finish(true));
    splitter.addEventListener('lostpointercapture', () => finish(true));
    window.addEventListener('blur', () => finish(true));
    splitter.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'Escape'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation();
      if (event.key === 'Escape') { finish(true); return; }
      const value = event.key === 'Home' ? 384 : Number(splitter.getAttribute('aria-valuenow')) + (event.key === 'ArrowLeft' ? 16 : -16);
      setWidth(value, true);
    });
    const horizontal = $('dockSplitter'); horizontal.tabIndex = 0;
    horizontal.setAttribute('aria-valuemin', '25'); horizontal.setAttribute('aria-valuemax', '68');
    const syncSplitValue = () => horizontal.setAttribute('aria-valuenow', String(
      parseFloat(document.querySelector('.editorShell').style.getPropertyValue('--editor-layer-height')) || 48));
    syncSplitValue();
    new MutationObserver(syncSplitValue).observe(document.querySelector('.editorShell'), { attributes: true, attributeFilter: ['style'] });
    horizontal.addEventListener('keydown', event => {
      if (!['ArrowUp', 'ArrowDown', 'Home'].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation();
      const current = parseFloat(document.querySelector('.editorShell').style.getPropertyValue('--editor-layer-height')) || 48;
      const value = event.key === 'Home' ? 48 : Math.max(25, Math.min(68, current + (event.key === 'ArrowUp' ? -3 : 3)));
      writeDockState({ layerPercent: value }); restoreDockState(); horizontal.setAttribute('aria-valuenow', String(value));
    });
  }
  function setupZoom() {
    const toolbar = document.createElement('div'); toolbar.className = 'workspaceZoom';
    function zoom(factor) {
      const amount = Math.max(.04, Math.min(8, canvas.getZoom() * factor));
      editorRenderer.beginHybridRender('zoom');
      canvas.zoomToPoint({ x: canvas.width / 2, y: canvas.height / 2 }, amount);
      styleActiveTransformControls(); syncSelectedShapeOutlines(); scheduleVisualGridLayerUpdate(); updateHud();
      if (editorRenderer.active) { editorRenderer.requestHybridRender(); editorRenderer.settleHybridRender(); }
      else requestCanvasRender();
    }
    toolbar.append(button('workspaceZoomOut', 'Zoom out', 'ZoomOut', () => zoom(1 / 1.2)), $('bottomZoom'),
      button('workspaceZoomIn', 'Zoom in', 'ZoomIn', () => zoom(1.2)),
      button('workspaceFit', 'Fit Vinyl', 'Scan', () => $('fitView').click()));
    toolbar.querySelectorAll('button').forEach(node => node.classList.add('workspaceIconOnly'));
    document.querySelector('.canvasStage').append(toolbar);
  }
  function refreshShortcuts() {
    if (!initialized) return;
    const toolActions = { v: 'selectTool', s: 'shapeLibrary', t: 'textTool', p: 'pixelArt', i: 'dropper', g: 'guides', o: 'overlay', r: 'sourceTool' };
    document.querySelectorAll('.toolButton').forEach(node => {
      const action = toolActions[node.dataset.toolKey] || 'makeMask';
      node.dataset.workspaceShortcut = shortcutFor(action);
    });
    const commands = { saveProject: 'saveProject', undoBtn: 'undo', redoBtn: 'redo', copyLayer: 'copy', pasteLayer: 'paste', duplicateLayer: 'duplicate', deleteLayer: 'delete' };
    Object.entries(commands).forEach(([id, action]) => { if (DEFAULT_SHORTCUTS[action]) $(id).dataset.workspaceShortcut = shortcutFor(action); });
  }
  function setupTooltips() {
    const tip = document.createElement('div'); tip.className = 'workspaceTooltip'; tip.id = 'workspaceTooltip'; tip.setAttribute('role', 'tooltip'); tip.hidden = true;
    tip.popover = 'manual';
    document.body.append(tip); let owner = null, pointerHeld = false, escapeHeld = false, revision = 0, hideTimer = null, clickPoint = null;
    let hoverTimer = null, hoverOwner = null, hideDeadline = null;
    function cancelShow() { clearTimeout(hoverTimer); hoverTimer = null; hoverOwner = null; }
    function cancelHide() { clearTimeout(hideTimer); hideTimer = null; hideDeadline = null; }
    function leave() { cancelHide(); hideDeadline = performance.now() + 180; hideTimer = setTimeout(hide, 180); }
    function hide() {
      cancelHide(); cancelShow();
      revision++;
      if (owner) {
        const descriptions = (owner.getAttribute('aria-describedby') || '').split(/\s+/).filter(id => id && id !== tip.id);
        if (descriptions.length) owner.setAttribute('aria-describedby', descriptions.join(' '));
        else owner.removeAttribute('aria-describedby');
      }
      if (tip.matches(':popover-open')) tip.hidePopover();
      owner = null; tip.hidden = true;
    }
    function transfer(node) {
      if (!(node instanceof Element) || !node.hasAttribute('title')) return;
      node.dataset.workspaceTooltip = node.getAttribute('title');
      node.removeAttribute('title');
    }
    function scan(node) {
      if (!(node instanceof Element)) return;
      transfer(node); node.querySelectorAll('[title]').forEach(transfer);
    }
    function show(target) {
      const node = target instanceof Element ? target.closest('[data-workspace-tooltip], [title]') : null;
      if (node) transfer(node);
      const text = node?.dataset.workspaceTooltip;
      hide();
      if (!text || !node.isConnected || !node.getClientRects().length) return;
      owner = node;
      const container = node.closest('dialog[open]') || document.body;
      if (tip.parentElement !== container) container.append(tip);
      tip.textContent = text + (node.dataset.workspaceShortcut ? ` (${node.dataset.workspaceShortcut})` : '');
      // Measure with full available width, not the previous owner's edge position.
      tip.style.left = '8px'; tip.style.top = '8px';
      tip.hidden = false; tip.showPopover();
      node.setAttribute('aria-describedby', [...new Set((node.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean).concat(tip.id))].join(' '));
      const rect = (node.closest('.dockTabs') || node).getBoundingClientRect();
      tip.style.left = `${Math.max(8, Math.min(node.getBoundingClientRect().left, innerWidth - tip.offsetWidth - 8))}px`;
      tip.style.top = `${rect.bottom + tip.offsetHeight + 12 < innerHeight ? rect.bottom + 8 : Math.max(8, rect.top - tip.offsetHeight - 8)}px`;
    }
    function hover(target) {
      const node = target instanceof Element ? target.closest('[data-workspace-tooltip], [title]') : null;
      if (node === owner && owner) { cancelHide(); return; }
      if (node === hoverOwner && hoverOwner) return;
      hide();
      if (!node) return;
      hoverOwner = node;
      hoverTimer = setTimeout(() => {
        cancelShow();
        if (!pointerHeld && !escapeHeld && node.matches(':hover')) show(node);
      }, 250);
    }
    // Keep legacy dynamic title setters, but never leave a second native popup.
    scan(document.body);
    new MutationObserver(records => {
      let changed = false;
      for (const record of records) {
        if (record.type === 'childList') record.addedNodes.forEach(scan);
        else { transfer(record.target); if (record.target === owner) changed = true; }
      }
      if (owner && (!owner.isConnected || !owner.getClientRects().length)) hide();
      else if (owner && changed) {
        const deadline = hideDeadline;
        show(owner);
        if (deadline !== null) {
          hideDeadline = deadline;
          hideTimer = setTimeout(hide, Math.max(0, deadline - performance.now()));
        }
      }
    }).observe(document.body, { subtree: true, childList: true, attributes: true,
      attributeFilter: ['title', 'data-workspace-shortcut', 'hidden', 'open'] });
    document.addEventListener('pointerover', event => {
      if (tip.contains(event.target)) { cancelHide(); return; }
      if (event.buttons || escapeHeld || (clickPoint && event.clientX === clickPoint.x && event.clientY === clickPoint.y)) { hide(); return; }
      clickPoint = null;
      const target = event.target instanceof Element ? event.target.closest('[data-workspace-tooltip], [title]') : null;
      if (target === owner && owner) cancelHide();
      else if (target) hover(target);
      else { cancelShow(); if (owner) leave(); }
    }, true);
    document.addEventListener('focusin', event => {
      // A menu can focus its first item inside showPopover(). Chromium forbids
      // another popover show until that operation has returned.
      const target = event.target, expected = revision;
      queueMicrotask(() => { if (expected === revision && !pointerHeld && !escapeHeld && document.activeElement === target) show(target); });
    });
    document.addEventListener('pointerout', event => {
      if (hoverOwner && !hoverOwner.contains(event.relatedTarget)) cancelShow();
      if (owner?.contains(event.relatedTarget) || tip.contains(event.relatedTarget)) cancelHide();
      else if (owner) leave();
    });
    document.addEventListener('focusout', hide);
    document.addEventListener('pointerdown', event => { pointerHeld = true; clickPoint = { x: event.clientX, y: event.clientY }; hide(); }, true);
    document.addEventListener('pointermove', event => {
      if (clickPoint && !event.buttons && (event.clientX !== clickPoint.x || event.clientY !== clickPoint.y)) {
        clickPoint = null; if (!escapeHeld) hover(event.target);
      }
    }, true);
    document.addEventListener('pointerup', () => { pointerHeld = false; }, true);
    document.addEventListener('pointercancel', () => { pointerHeld = false; hide(); }, true);
    window.addEventListener('blur', () => { pointerHeld = false; escapeHeld = false; clickPoint = null; hide(); });
    document.addEventListener('scroll', hide, true); window.addEventListener('resize', hide);
    document.addEventListener('close', hide, true);
    document.addEventListener('toggle', () => { if (owner && !owner.getClientRects().length) hide(); }, true);
    window.addEventListener('keydown', event => { if (event.key === 'Escape') { escapeHeld = true; hide(); } }, true);
    window.addEventListener('keyup', event => { if (event.key === 'Escape') escapeHeld = false; }, true);
  }
  function init() {
    if (initialized) return;
    initialized = true;
    document.documentElement.classList.add('workspaceRedesign');
    setupMenus(); setupTools(); setupLayers(); setupProperties(); setupDock(); setupZoom(); setupTooltips(); refreshShortcuts();
    // Existing command owners may replace captions as selection changes.
    const observer = new MutationObserver(() => {
      for (const [node, config] of iconButtons) {
        if (!node.querySelector(':scope > .workspaceIcon')) decorate(node, config.symbol, config.iconOnly);
      }
    });
    for (const node of iconButtons.keys()) observer.observe(node, { childList: true });
    root.KfpsDocking?.init();
    scheduleCanvasResize();
  }
  root.KfpsWorkspace = Object.freeze({ init, icon, refreshShortcuts, resetLayout, attachMenu });
})(window);
