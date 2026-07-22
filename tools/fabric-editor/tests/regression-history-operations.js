async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const shapes = Array.from({ length: 100 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [80 + index, 120, 210, 255],
      data: [index * 3, -index * 2, 0.35, 0.35, index % 12, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    clearAutosave();
    await loadPayload({ shapes });
    const baseline = JSON.stringify(snapshotEditorState());

    canvas.setActiveObject(vinylObjects()[10]);
    toggleSelectedMaskLayers();
    canvas.setActiveObject(vinylObjects()[20]);
    await duplicateSelected();
    canvas.setActiveObject(vinylObjects()[30]);
    deleteSelected();
    canvas.setActiveObject(vinylObjects()[40]);
    moveSelected(1);
    const finalState = JSON.stringify(snapshotEditorState());
    const finalCount = vinylObjects().length;

    for (let index = 0; index < 4; index += 1) await undo();
    const undoState = JSON.stringify(snapshotEditorState());
    for (let index = 0; index < 4; index += 1) await redo();
    const redoState = JSON.stringify(snapshotEditorState());
    return {
      finalCount,
      baselineRestored: undoState === baseline,
      finalRestored: redoState === finalState,
      maskCountAfterRedo: vinylObjects().filter((object) => object.kloudy.mask).length,
      historyEntries: history.length,
      allIdsUnique: new Set(vinylObjects().map((object) => object.kloudy.editor_id)).size === vinylObjects().length,
    };
  });
}
