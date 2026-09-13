async page => page.evaluate(async () => {
  await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({ type: 1048677,
    color: [70, 150, 210, 255], data: [i % 60 * 20, Math.floor(i / 60) * 20, .1, .1, 0, 0, 0] })) });
  const predicate = vinylObjectRegistry.predicate;
  let filtered = 0;
  vinylObjectRegistry.predicate = object => { filtered++; return predicate(object); };
  try {
    vinylObjectRegistry.invalidate();
    const first = vinylObjects();
    const built = filtered;
    for (let i = 0; i < 100; i++) if (vinylObjects() !== first) throw new Error("Unchanged public Fabric snapshots rebuilt the registry");
    if (filtered !== built) throw new Error("Unchanged registry repeated the full filter/index allocation");
    const originalFirst = first[0], last = first.at(-1);
    KfpsFabricAdapter.moveObjectTo(canvas, last, canvas.getObjects().indexOf(originalFirst));
    if (vinylObjects()[0] !== last) throw new Error("Direct same-size Fabric reorder left stale order");
    const fresh = await makeFabricObject({ type: 1048677, color: [10, 20, 30, 255], data: [200, 300, .2, .2, 0, 0, 0] });
    discardFabricObject(last); canvas.add(fresh);
    if (vinylObjects().includes(last) || vinylObjects().at(-1) !== fresh || vinylObjects().length !== 3000) throw new Error("Same-size replacement left stale membership");
    const guide = new fabric.Line([0, 0, 100, 0]); guide.kloudyGuide = true;
    canvas.add(guide);
    if (!editorGuideObjects().includes(guide) || vinylObjects().includes(guide)) throw new Error("Helper membership leaked between registries");
    canvas.remove(guide); guide.dispose?.();
    if (editorGuideObjects().includes(guide)) throw new Error("Removed helper retained in registry");
    establishLoadedHistoryBoundary("registry structural test");
    const before = JSON.stringify(snapshotShapes());
    selectObjects(vinylObjects().slice(0, 40), "registry history");
    nudgeSelected(1, 0); flushPendingNudgeHistory();
    const moved = JSON.stringify(snapshotShapes());
    await undo();
    if (JSON.stringify(snapshotShapes()) !== before) throw new Error("Cached order changed undo artwork");
    await redo();
    if (JSON.stringify(snapshotShapes()) !== moved || moved === before) throw new Error("Cached order changed redo artwork");
    await flushPendingAutosave();
    if (JSON.stringify((await readAutosavePayload()).shapes) !== moved) throw new Error("Registry cache changed recovery order");
    return { layers: 3000, warmReads: 100, warmRefilters: 0, reorder: true, sameSizeReplacement: true, helpers: true, historyAndRecoveryExact: true };
  } finally { vinylObjectRegistry.predicate = predicate; vinylObjectRegistry.invalidate(); }
})
