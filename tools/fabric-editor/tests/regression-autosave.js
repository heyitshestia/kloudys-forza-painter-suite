async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [100, 160, 220, 255],
      data: [(index % 60) * 20, -Math.floor(index / 60) * 20, 0.18, 0.18, 0, 0, 0],
    }));
    clearAutosave();
    await loadPayload({ shapes });
    const target = vinylObjects()[0];
    target.set({ left: target.left + 37 });
    target.setCoords();
    pushHistory("autosave regression");
    await new Promise((resolve) => setTimeout(resolve, 500));
    const raw = localStorage.getItem(AUTOSAVE_KEY) || "";
    const saved = raw ? JSON.parse(raw) : null;
    const savedShape = saved?.shapes?.find((shape) => shape.editor_id === target.kloudy.editor_id);
    const expectedX = objectToShape(target, { includeEditorMeta: true }).data[0];
    clearAutosave();
    return {
      bytes: raw.length,
      layers: saved?.shapes?.length || 0,
      latestTransformSaved: Math.abs(Number(savedShape?.data?.[0]) - expectedX) < 0.001,
      editorIdsSaved: saved?.shapes?.every((shape) => Boolean(shape.editor_id)) || false,
      historyInternalsExcluded: !raw.includes("__historySignature"),
    };
  });
}
