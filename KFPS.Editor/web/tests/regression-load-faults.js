async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  const fixture = options.project ? h.input(options).project : null;
  if (fixture) await h.setup(page, output, options);
  return page.evaluate(async fixture => {
  const checks = [];
  const assert = (ok, message) => { if (!ok) throw Error(message); checks.push(message); };
  const shapes = fixture?.shapes || Array.from({ length: 2400 }, (_, i) => ({ type: 1048677,
    color: [70, 120, 190, 255], data: [(i % 60) * 12, Math.floor(i / 60) * 12, .06, .06, 0, 0, 0] }));
  const reference = fixture?.editor_source_overlay || { kind: "image", data_url: 'data:image/svg+xml,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="5888" height="2816"><rect width="5888" height="2816" fill="#6b8899"/></svg>'),
    file_name: "Synthetic reference.svg", transform: { opacity: .6 } };
  await loadProjectPayload({ shapes, name: "Fault A", editor_source_overlay: reference,
    editor_guides: { guides: [{ id: "diagonal", x1: 0, y1: 0, x2: 200, y2: 200 }] } });
  await saveProject();
  const receipt = editorProjects.association;
  const retained = JSON.stringify(snapshotEditorState()), source = JSON.stringify(editorReference.sourceOverlayProjectState());
  const state = currentHistoryState();
  const faults = [
    ["build", () => makeFabricObject, f => { makeFabricObject = f; }, 30],
    ["partial add", () => canvas.add, f => { canvas.add = f; }, 30],
    ["partial remove", () => canvas.remove, f => { canvas.remove = f; }, 30],
    ["coordinate installation", () => syncCanvasObjectCoords, f => { syncCanvasObjectCoords = f; }, 1],
    ["baseline installation", () => editorHistory.installBaseline, f => { editorHistory.installBaseline = f; }, 1],
  ];
  for (const [name, get, set, threshold] of faults) {
    const original = get(); let calls = 0, rejected = false;
    set(function (...args) { if (++calls === threshold) throw Error(`Injected ${name}`); return original.apply(this, args); });
    try { await loadProjectPayload({ shapes, name: `Rejected ${name}` }); }
    catch (_) { rejected = true; }
    finally { set(original); }
    assert(rejected && currentHistoryState() === state, `${name}: retained baseline`);
    assert(JSON.stringify(snapshotEditorState()) === retained && JSON.stringify(editorReference.sourceOverlayProjectState()) === source,
      `${name}: exact scene, guides and reference`);
    assert(editorProjects.association?.fingerprint === receipt.fingerprint && !documentDirty, `${name}: retained clean association`);
  }
  for (const file of [new File(['{'], 'Broken.fabric-project.json'),
    new File([JSON.stringify({ name: "Invalid", shapes: [null] })], 'Invalid.fabric-project.json')]) {
    try { await loadProjectFile(file); } catch (_) {}
    assert(editorProjects.association?.fingerprint === receipt.fingerprint, "file-read rejection retains receipt");
  }
  // A pending native write may finish after a failed attempt, but never clean a replacement.
  for (const replace of [false, true]) {
    const original = saveProjectToAppFolder;
    let release, enter;
    const gate = new Promise(resolve => { release = resolve; });
    const ready = new Promise(resolve => { enter = resolve; });
    saveProjectToAppFolder = async (...args) => { const result = await original(...args); enter(); await gate; return result; };
    let saving;
    try {
      vinylObjects()[0].left += 7; pushHistory("before pending save");
      saving = saveProject(); await ready;
      if (replace) await loadProjectPayload({ shapes, name: "Accepted replacement" });
      else { try { await loadProjectPayload({ bad: true }); } catch (_) {} }
      const acceptedState = currentHistoryState(), acceptedSavedState = savedHistoryState, acceptedDirty = documentDirty;
      release(); await saving;
      assert(replace ? documentDirty === acceptedDirty && currentHistoryState() === acceptedState
        && savedHistoryState === acceptedSavedState && !editorProjects.association && currentProjectName === "Accepted replacement"
        : !documentDirty && editorProjects.association, replace ? "late A write does not clean B" : "failed B does not orphan pending A write");
    } finally { release(); if (saving) await saving; saveProjectToAppFolder = original; }
  }
  // Edits during reference restoration retain the accepted disk target but stay dirty.
  const result = await editorProjects.save("Restoring B", { shapes, name: "Restoring B" }, null);
  const originalRestore = editorReference.restoreSourceOverlayFromProject;
  let release, enter;
  const gate = new Promise(resolve => { release = resolve; });
  const ready = new Promise(resolve => { enter = resolve; });
  editorReference.restoreSourceOverlayFromProject = async (...args) => { enter(); await gate; return originalRestore(...args); };
  try {
    const loading = loadProjectPayload({ shapes, name: "Restoring B", editor_source_overlay: reference }, "Restoring B", { receipt: result.receipt });
    await ready;
    assert(editorProjects.association?.fingerprint === result.receipt.fingerprint, "receipt attached before reference restore finishes");
    vinylObjects()[0].left += 9; pushHistory("edit during reference restore");
    release(); await loading;
    assert(documentDirty && editorProjects.association?.fingerprint === result.receipt.fingerprint, "restoration preserves newer edits and receipt");
    await saveProject();
    assert(!documentDirty, "edited-during-restore project saves normally");
  } finally { release(); editorReference.restoreSourceOverlayFromProject = originalRestore; }
  await flushPendingAutosave();
  const protectedCopy = await readAutosavePayload();
  assert(JSON.stringify(protectedCopy.shapes) === JSON.stringify(snapshotShapes()) && protectedCopy.editor_source_overlay,
    "disk/browser recovery matches accepted content and reference");
  await clearAutosave(); documentDirty = false;
  return { passed: true, checks, layers: shapes.length, handmadeFixture: Boolean(fixture), controlledFaultInjection: true };
  }, fixture);
}
