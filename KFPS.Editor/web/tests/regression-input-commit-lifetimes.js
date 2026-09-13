async (page, options = {}) => page.evaluate(async ({ characterize }) => {
  const results = [];
  const fixture = () => ({ shapes: Array.from({ length: 300 }, (_, i) => ({
    type: 1048677, data: [i % 20 * 23, Math.floor(i / 20) * 25, .1, .12, 0, 0, 0], color: [80, 120, 220, 255],
  })) });
  for (const [name, count, hook, action] of [
    ['batch appearance', 3, 'refreshColorUi', () => { $('colorPicker').value = '#cc2244'; applySelectionFields(); }],
    ['numeric transform', 1, 'syncMaskPreviewOutlines', () => { $('rotInput').value = '45'; applySelectionFields(); }],
    ['nudge', 1, 'updateSelectionPanel', () => nudgeSelected(3, 4)],
  ]) {
    await loadPayload(fixture());
    canvas.setActiveObject(count > 1 ? styledActiveSelection(vinylObjects().slice(0, count)) : vinylObjects()[0]);
    updateSelectionPanel();
    const before = JSON.stringify(snapshotShapes()), index = editorHistory.index;
    const original = window[hook]; let injected = false;
    window[hook] = (...args) => {
      if (!injected && JSON.stringify(snapshotShapes()) !== before) { injected = true; throw Error('Injected input display failure'); }
      return original(...args);
    };
    try { action(); } catch (_) {} finally { window[hook] = original; }
    flushPendingNudgeHistory();
    document.querySelectorAll('dialog[open]').forEach(d => d.close());
    const changed = JSON.stringify(snapshotShapes()) !== before;
    const committed = editorHistory.index === index + 1 && JSON.stringify(snapshotShapes()) === JSON.stringify(currentHistoryState().shapes);
    let recovered = false, undone = false;
    if (committed) {
      await flushPendingAutosave(); recovered = editorRecovery.status.serverOk === true;
      await undo(); undone = JSON.stringify(snapshotShapes()) === before;
    }
    results.push({ name, injected, changed, committed, recovered, undone, passed: injected && changed && committed && recovered && undone });
  }
  await loadPayload(fixture());
  editorRenderer.reset();
  const renderer = editorRenderer.initHybridRenderer(), gl = renderer.gl;
  const original = gl.bufferData; let injected = false;
  gl.bufferData = function (...args) { injected = true; throw Error('Injected prewarm allocation failure'); };
  let opened = false;
  try { opened = await loadPayload(fixture()); } catch (_) {} finally { gl.bufferData = original; }
  const fallback = Boolean(editorRenderer.disabledReason);
  results.push({ name: 'GPU prewarm fallback', injected, opened, fallback, layers: vinylObjects().length,
    passed: injected && opened === true && fallback && vinylObjects().length === 300 });
  if (!characterize && results.some(item => !item.passed)) throw Error(JSON.stringify(results));
  return results;
}, options)
