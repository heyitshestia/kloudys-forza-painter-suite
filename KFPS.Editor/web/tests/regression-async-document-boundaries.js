async page => {
  return page.evaluate(async () => {
    const assert = (condition, message) => { if (!condition) throw new Error(message); };
    const shape = (x = 0) => ({ type: 1048677, data: [x, 0, 1, 1, 0, 0, 0], color: [70, 120, 190, 255] });
    const blank = async () => { documentDirty = false; await startBlankCanvas(); };
    const results = [];
    for (const project of [false, true]) {
      await blank();
      const original = editorPersistence.request;
      let release, entered;
      const ready = new Promise(resolve => { entered = resolve; });
      const gate = new Promise(resolve => { release = resolve; });
      editorPersistence.request = async function(action, ...args) {
        if (action === "parseFile") { entered(); await gate; }
        return original.call(this, action, ...args);
      };
      try {
        const file = new File([JSON.stringify({ name: "Old file", shapes: [shape()] })], "Old file.json");
        const loading = project ? loadProjectFile(file) : loadJsonFile(file);
        await ready; await blank(); release(); await loading;
        assert(!vinylObjects().length && loadedName === "untitled" && currentProjectName === null, "A late parsed file overwrote New");
        results.push(project ? "project parse cancellation" : "JSON parse cancellation");
      } finally { release(); editorPersistence.request = original; }
    }
    await blank();
    await loadPayload({ shapes: [shape(), { ...shape(100), type: 1048678 }] });
    canvas.setActiveObject(vinylObjects()[1]); deleteSelected();
    const originalBuild = makeFabricObject;
    let release, entered;
    const gate = new Promise(resolve => { release = resolve; });
    const ready = new Promise(resolve => { entered = resolve; });
    makeFabricObject = async (...args) => { entered(); await gate; return originalBuild(...args); };
    try {
      const restoring = undo(); await ready;
      const queued = redo();
      await blank(); release(); await restoring; await queued;
      assert(!vinylObjects().length && editorHistory.index === 0 && !historyLocked, "History crossed a document boundary");
      results.push("active and queued history cancellation");
    } finally { release(); makeFabricObject = originalBuild; }

    const transparent = { name: "Transparent layers", shapes: [shape(), { ...shape(100), color: [50, 100, 150, 0] }] };
    await loadProjectPayload(transparent);
    const exact = JSON.stringify(snapshotShapes());
    const recovery = autosavePayloadFromState(currentHistoryState());
    await blank(); assert(await recoverAutosavePayload(recovery), "Transparent-layer recovery failed");
    assert(JSON.stringify(snapshotShapes()) === exact && vinylObjects()[1].opacity === 0, "Transparent layer was lost during recovery");
    results.push("transparent project and recovery roundtrip");

    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"><g id="color"><rect width="16" height="16" fill="red"/></g></svg>';
    await editorReference.restoreSourceOverlayFromProject({ kind: "layered_svg", svg_text: svg, file_name: "Existing.svg" });
    const reference = JSON.stringify(editorReference.sourceOverlayProjectState());
    editorReference.addOverlayFile(new File(["<not-svg"], "Broken.svg", { type: "image/svg+xml" }));
    await new Promise(resolve => setTimeout(resolve, 50));
    assert(JSON.stringify(editorReference.sourceOverlayProjectState()) === reference, "Broken SVG replacement changed the previous reference");
    results.push("invalid SVG preserves previous reference");

    const NativeReader = window.FileReader;
    let deliver, aborted = false;
    window.FileReader = class {
      readyState = 0;
      readAsText() { this.readyState = 1; this.result = svg; deliver = () => this.onload?.(); }
      abort() { aborted = true; this.readyState = 2; this.onloadend?.(); }
    };
    try {
      editorReference.addOverlayFile(new File([svg], "Delayed.svg", { type: "image/svg+xml" }));
      editorReference.removeOverlay(); deliver(); await nextFrame();
      assert(!editorReference.image && !editorReference.layered && !editorReference.source, "A late FileReader resurrected a removed reference");
      assert(aborted, "Removed reference kept reading the file");
      results.push("FileReader cancellation after removal");
    } finally { window.FileReader = NativeReader; }
    return { results };
  });
}
