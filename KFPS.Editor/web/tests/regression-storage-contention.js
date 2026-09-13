async page => page.evaluate(async () => {
  await loadProjectPayload({ name: "Contention", shapes: Array.from({ length: 2800 }, (_, i) => ({
    type: 1048677, color: [70, 130, 190, 255], data: [i % 70 * 12, Math.floor(i / 70) * 12, .05, .05, 0, 0, 0],
  })) });
  await flushPendingAutosave();
  const rows = [];
  for (const concurrent of [false, true, true, false]) {
    const payload = autosavePayloadFromState(currentHistoryState());
    // A syntactically valid, near-capacity file; test the real File.text/JSON/clone path.
    const file = concurrent ? new File(['{"shapes":[],"padding":"', "x".repeat(149 * 1024 * 1024), '"}'], "Near capacity.fabric-project.json") : null;
    let loading = null, frames = [], last = performance.now(), running = true;
    const frame = () => { const now = performance.now(); frames.push(now - last); last = now; if (running) requestAnimationFrame(frame); };
    requestAnimationFrame(frame);
    const start = performance.now();
    if (file) loading = editorPersistence.request("parseFile", { file });
    payload.shapes = payload.shapes.slice(); payload.shapes[0] = { ...payload.shapes[0], score: start };
    writeAutosavePayload(payload); await flushPendingAutosave();
    const recoveryMs = performance.now() - start;
    if (!editorRecovery.status.serverOk) throw Error("Ordinary recovery lost its disk acknowledgment under parse load");
    if (loading) { const parsed = await loading; if (parsed.padding.length !== 149 * 1024 * 1024) throw Error("Parse truncated input"); }
    await new Promise(resolve => setTimeout(resolve, 200)); running = false;
    rows.push({ concurrent, fileBytes: file?.size || 0, recoveryMs, totalMs: performance.now() - start, maxFrameMs: Math.max(...frames) });
  }
  await clearAutosave(); documentDirty = false;
  return { passed: true, rows, policy: "ABBA near-capacity parse versus ordinary 2800-layer recovery; real worker and disk, no forced GC" };
})
