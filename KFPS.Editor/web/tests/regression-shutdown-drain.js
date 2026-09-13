async (page, options = {}) => page.evaluate(async ({ characterize }) => {
  await loadPayload({ shapes: Array.from({ length: 300 }, (_, i) => ({ type: 1048677,
    data: [i % 20 * 25, Math.floor(i / 20) * 25, .1, .12, 0, 0, 0], color: [80, 120, 220, 255] })) });
  await flushPendingAutosave();
  const request = editorPersistence.request.bind(editorPersistence);
  let release, held = false;
  editorPersistence.request = async (operation, data) => {
    if (operation === 'recovery' && !held) { held = true; await new Promise(resolve => { release = resolve; }); }
    return request(operation, data);
  };
  vinylObjects()[0].set({ angle: 30 }); pushHistory('field edit');
  const first = flushPendingAutosave();
  if (!release) throw Error('First recovery did not enter the controlled transport wait');
  vinylObjects()[0].set({ angle: 60 }); pushHistory('field edit');
  const expected = JSON.stringify(currentHistoryState().shapes);
  window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: false }));
  release(); await first;
  if (typeof editorShutdownPromise !== 'undefined' && editorShutdownPromise) await editorShutdownPromise;
  const response = await fetch('/api/fabric-editor/autosave', { cache: 'no-store' });
  const stored = await response.json();
  const result = { held, latestStored: JSON.stringify(stored.payload?.shapes || stored.shapes) === expected,
    workerDisposed: editorPersistence.disposed, pendingJobs: editorPersistence.pending.size };
  if (!characterize && (!result.latestStored || !result.workerDisposed || result.pendingJobs)) throw Error(JSON.stringify(result));
  return result;
}, options)
