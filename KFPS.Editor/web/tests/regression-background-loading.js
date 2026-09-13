async page => {
  const result = await page.evaluate(async () => {
    const shapes = Array.from({ length: 1400 }, (_, i) => ({ type: 1048677,
      color: [70, 150, 210, 255], data: [i % 50 * 20 - 500, Math.floor(i / 50) * 20 - 300, .1, .1, 0, 0, 0],
      editor_group_id: `g${Math.floor(i / 20)}`, editor_group_name: `Group ${Math.floor(i / 20)}` }));
    const json = new File([JSON.stringify({ shapes })], "background.json", { type: "application/json" });
    const project = new File([JSON.stringify({ shapes, name: "Background loading" })], "background.fabric-project.json", { type: "application/json" });
    const originalText = Blob.prototype.text;
    const originalFetch = window.fetch;
    const originalReader = window.FileReader;
    let mainFileReads = 0, mainDocumentReads = 0, oversizedReads = 0;
    Blob.prototype.text = function () { mainFileReads++; throw new Error("Document decoded on UI thread"); };
    window.fetch = (url, options) => {
      if (String(url).includes("/project-file?")) { mainDocumentReads++; throw new Error("Project parsed on UI thread"); }
      return originalFetch(url, options);
    };
    try {
      await loadJsonFile(json);
      if (vinylObjects().length !== 1400) throw new Error("Worker JSON import lost layers");
      await loadProjectFile(project);
      const expected = JSON.stringify(snapshotShapes());
      await saveProject();
      const data = await readEditorDocument(PROJECT_FILE_API + "?id=Background%20loading.fabric-project.json");
      await loadProjectPayload(data.payload);
      if (JSON.stringify(snapshotShapes()) !== expected || documentDirty) throw new Error("Worker project roundtrip changed data");
      let malformed = false;
      try { await loadJsonFile(new File(["{invalid"], "invalid.json")); }
      catch (_) { malformed = true; }
      clearBusy();
      if (!malformed || JSON.stringify(snapshotShapes()) !== expected) throw new Error("Malformed JSON replaced the current artwork");
      window.FileReader = class { constructor() { oversizedReads++; throw new Error("Oversized reference was read"); } };
      editorReference.addOverlayFile({ size: EDITOR_REFERENCE_MAX_BYTES + 1, name: "oversized.png", type: "image/png" });
      if (mainFileReads || mainDocumentReads || oversizedReads) throw new Error("Loading bypassed background/size guards");
      return { layers: 1400, exact: true, mainFileReads, mainDocumentReads, oversizedReads, malformedPreserved: true };
    } finally {
      Blob.prototype.text = originalText;
      window.fetch = originalFetch;
      window.FileReader = originalReader;
    }
  });
  return result;
}
