async page => {
  const results = await page.evaluate(async () => {
    const results = [];
    const shape = x => ({ type: 1048677, data: [x, 0, 0.5, 0.5, 0, 0, 0], color: [80, 140, 200, 255] });
    const blank = async () => { document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close()); documentDirty = false; await startBlankCanvas(); };
    for (const operation of ["add", "duplicate", "paste", "replace"]) {
      await blank(); await loadPayload({ shapes: [shape(0)] });
      canvas.setActiveObject(vinylObjects()[0]); copySelectedLayers();
      let release, entered;
      const gate = new Promise(resolve => { release = resolve; });
      const ready = new Promise(resolve => { entered = resolve; });
      const original = makeFabricObject;
      makeFabricObject = async (...args) => { entered(); await gate; return original(...args); };
      try {
        const pending = operation === "add" ? addShape("Primitives", 2)
          : operation === "duplicate" ? duplicateSelected()
            : operation === "paste" ? pasteCopiedLayers() : replaceSelectedShapes("Primitives", 2);
        await ready; await blank(); release(); await pending;
        results.push({ operation, preserved: vinylObjects().length === 0 && editorHistory.index === 0, layers: vinylObjects().length });
      } finally { release(); makeFabricObject = original; }
    }
    await blank(); await loadPayload({ shapes: [shape(0), shape(100)] });
    selectAllLayers();
    const before = JSON.stringify(snapshotShapes()), index = editorHistory.index;
    const originalAdd = canvas.add;
    let injected = false;
    canvas.add = function(...objects) {
      if (!injected && objects.some(object => object.kloudy)) { injected = true; throw new Error("Injected shape installation failure"); }
      return originalAdd.apply(this, objects);
    };
    let failed = false;
    try { await replaceSelectedShapes("Primitives", 2); } catch (_error) { failed = true; }
    finally { canvas.add = originalAdd; }
    results.push({ operation: "replacement installation failure", preserved: injected && failed && before === JSON.stringify(snapshotShapes()) && index === editorHistory.index });

    await blank(); await loadPayload({ shapes: Array.from({ length: 2999 }, (_, i) => shape(i)) });
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    const original = makeFabricObject;
    makeFabricObject = async (...args) => { await gate; return original(...args); };
    try {
      const first = addShape("Primitives", 1), second = addShape("Primitives", 2);
      release(); await first; await second;
      results.push({ operation: "concurrent add at capacity", preserved: vinylObjects().length === 3000, layers: vinylObjects().length });
    } finally { release(); makeFabricObject = original; }
    return results;
  });
  const failures = results.filter(result => !result.preserved);
  if (failures.length) throw new Error(JSON.stringify(failures));
  return { results };
}
