async (page) => {
  page.setDefaultTimeout(240000);
  return page.evaluate(async () => {
    const makeShapes = (count, withEditorIds = false) => Array.from({ length: count }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [70 + index % 170, 110 + index % 90, 210, 255],
      data: [-650 + (index % 30) * 44, 420 - Math.floor(index / 30) * 42, 0.22, 0.22, index % 19, 0, 0],
      ...(withEditorIds ? { editor_id: `e${index + 1}` } : {}),
    }));

    const stateSummary = () => {
      const objects = vinylObjects();
      const ids = objects.map((object) => String(object.kloudy?.editor_id || ""));
      const seen = new Set();
      const duplicateIds = [];
      ids.forEach((editorId) => {
        if (seen.has(editorId)) duplicateIds.push(editorId);
        else seen.add(editorId);
      });
      return {
        count: objects.length,
        uniqueIds: seen.size,
        hidden: objects.filter((object) => object.visible === false).length,
        duplicateIds,
      };
    };

    const comparableState = (state) => JSON.stringify({
      shapes: state?.shapes || [],
      editor_guides: state?.editor_guides || null,
      editor_collapsed_groups: state?.editor_collapsed_groups || [],
    });

    const runHistoryCase = async (count, withEditorIds = false) => {
      endHybridRenderNow();
      clearAutosave();
      nextEditorObjectId = 1;
      await loadPayload({ shapes: makeShapes(count, withEditorIds) });
      const nextIdAfterLoad = nextEditorObjectId;
      const baseline = JSON.stringify(snapshotEditorState());
      canvas.setActiveObject(vinylObjects()[Math.floor(count / 2)]);
      beginHybridRender("history threshold regression");
      await duplicateSelected();
      const duplicated = stateSummary();
      await undo();
      const undone = stateSummary();
      const baselineRestored = JSON.stringify(snapshotEditorState()) === baseline;
      await redo();
      const redone = stateSummary();
      endHybridRenderNow();
      return {
        count,
        withEditorIds,
        nextIdAfterLoad,
        duplicated,
        undone,
        redone,
        baselineRestored,
      };
    };

    const runMaximumLayerHistoryCase = async () => {
      endHybridRenderNow();
      clearAutosave();
      nextEditorObjectId = 1;
      await loadPayload({ shapes: makeShapes(MAX_VINYL_LAYERS, true) });
      const baseline = JSON.stringify(snapshotEditorState());
      canvas.setActiveObject(vinylObjects()[1500]);
      deleteSelected();
      const deleted = stateSummary();
      await undo();
      const undone = stateSummary();
      const baselineRestored = JSON.stringify(snapshotEditorState()) === baseline;
      await redo();
      const redone = stateSummary();
      endHybridRenderNow();
      return { deleted, undone, redone, baselineRestored };
    };

    const runRapidHistoryCase = async () => {
      endHybridRenderNow();
      clearAutosave();
      nextEditorObjectId = 1;
      await loadPayload({ shapes: makeShapes(300, true) });
      const target = vinylObjects()[150];
      for (let index = 1; index <= 8; index += 1) {
        target.set({ left: target.left + index });
        target.setCoords();
        pushHistory(`rapid history ${index}`);
      }
      const expectedUndoIndex = historyIndex - 5;
      const expectedUndoState = comparableState(history[expectedUndoIndex]);
      await Promise.all([undo(), undo(), undo(), undo(), undo()]);
      const undoMatches = historyIndex === expectedUndoIndex
        && comparableState(snapshotEditorState()) === expectedUndoState;
      const expectedRedoIndex = historyIndex + 3;
      const expectedRedoState = comparableState(history[expectedRedoIndex]);
      await Promise.all([redo(), redo(), redo()]);
      const redoMatches = historyIndex === expectedRedoIndex
        && comparableState(snapshotEditorState()) === expectedRedoState;
      endHybridRenderNow();
      return { undoMatches, redoMatches, historyIndex, expectedRedoIndex, state: stateSummary() };
    };

    const runDuplicateUndoRaceCase = async () => {
      endHybridRenderNow();
      clearAutosave();
      nextEditorObjectId = 1;
      await loadPayload({ shapes: makeShapes(300, true) });
      const baseline = JSON.stringify(snapshotEditorState());
      canvas.setActiveObject(vinylObjects()[150]);
      const duplicatePromise = duplicateSelected();
      const undoPromise = undo();
      await Promise.all([duplicatePromise, undoPromise]);
      const undoState = stateSummary();
      const undoMatches = undoState.count === 300
        && undoState.uniqueIds === 300
        && JSON.stringify(snapshotEditorState()) === baseline;
      await redo();
      const redoState = stateSummary();
      const redoMatches = redoState.count === 301 && redoState.uniqueIds === 301;
      endHybridRenderNow();
      return { undoMatches, redoMatches, undoState, redoState };
    };

    const sampleHybridOverlay = async () => {
      endHybridRenderNow();
      await loadPayload({ shapes: makeShapes(HYBRID_RENDER_MIN_LAYERS) });
      const marker = document.createElement("canvas");
      marker.width = 4;
      marker.height = 4;
      const context = marker.getContext("2d");
      context.fillStyle = "#ff0000";
      context.fillRect(0, 0, 2, 2);
      context.fillStyle = "#00ff00";
      context.fillRect(2, 0, 2, 2);
      context.fillStyle = "#0000ff";
      context.fillRect(0, 2, 2, 2);
      context.fillStyle = "#ffff00";
      context.fillRect(2, 2, 2, 2);
      await loadOverlayImageFromUrl(marker.toDataURL("image/png"), "hybrid-orientation.png");
      overlayLayerMode = "above";
      overlayImage.set({ left: 0, top: 0, scaleX: 120, scaleY: 120, angle: 0, opacity: 1 });
      overlayImage.setCoords();
      beginHybridRender("overlay orientation regression");
      hybridRenderNow();

      const gl = hybridRenderer.gl;
      const readLocal = (x, y) => {
        const world = fabric.util.transformPoint(new fabric.Point(x, y), overlayImage.calcTransformMatrix());
        const screen = fabric.util.transformPoint(world, canvas.viewportTransform);
        const pixel = new Uint8Array(4);
        gl.readPixels(
          Math.max(0, Math.min(hybridRenderer.element.width - 1, Math.round(screen.x))),
          Math.max(0, Math.min(hybridRenderer.element.height - 1, hybridRenderer.element.height - 1 - Math.round(screen.y))),
          1,
          1,
          gl.RGBA,
          gl.UNSIGNED_BYTE,
          pixel,
        );
        return Array.from(pixel);
      };
      const samples = {
        topLeft: readLocal(-1, -1),
        topRight: readLocal(1, -1),
        bottomLeft: readLocal(-1, 1),
        bottomRight: readLocal(1, 1),
      };
      endHybridRenderNow();
      removeOverlay();
      return samples;
    };

    const assertHistoryCase = (result) => {
      const expectedDuplicated = result.count + 1;
      if (result.duplicated.count !== expectedDuplicated || result.duplicated.uniqueIds !== expectedDuplicated) {
        throw new Error(`${result.count}-layer duplicate produced missing or duplicate editor IDs (next after load ${result.nextIdAfterLoad}): ${JSON.stringify(result.duplicated)}`);
      }
      if (result.undone.count !== result.count || result.undone.uniqueIds !== result.count || !result.baselineRestored) {
        throw new Error(`${result.count}-layer undo did not restore the exact baseline.`);
      }
      if (result.redone.count !== expectedDuplicated || result.redone.uniqueIds !== expectedDuplicated) {
        throw new Error(`${result.count}-layer redo lost or duplicated a layer.`);
      }
      if (result.duplicated.hidden || result.undone.hidden || result.redone.hidden) {
        throw new Error(`${result.count}-layer history operation left layers hidden.`);
      }
    };

    const closeColor = (actual, expected) => expected.every((value, index) => Math.abs(actual[index] - value) <= 3);

    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    const plain = [];
    for (const count of [299, 300, 301]) plain.push(await runHistoryCase(count, false));
    const persistedIds = await runHistoryCase(300, true);
    const maximumLayers = await runMaximumLayerHistoryCase();
    const rapidHistory = await runRapidHistoryCase();
    const duplicateUndoRace = await runDuplicateUndoRaceCase();
    const overlay = await sampleHybridOverlay();
    plain.forEach(assertHistoryCase);
    assertHistoryCase(persistedIds);
    if (
      maximumLayers.deleted.count !== MAX_VINYL_LAYERS - 1
      || maximumLayers.undone.count !== MAX_VINYL_LAYERS
      || maximumLayers.redone.count !== MAX_VINYL_LAYERS - 1
      || !maximumLayers.baselineRestored
    ) throw new Error("3,000-layer delete history did not round-trip exactly.");
    if (!rapidHistory.undoMatches || !rapidHistory.redoMatches) {
      throw new Error(`Rapid history operations raced: ${JSON.stringify(rapidHistory)}`);
    }
    if (!duplicateUndoRace.undoMatches || !duplicateUndoRace.redoMatches) {
      throw new Error(`Duplicate/undo operations raced: ${JSON.stringify(duplicateUndoRace)}`);
    }
    const expectedOverlay = {
      topLeft: [255, 0, 0, 255],
      topRight: [0, 255, 0, 255],
      bottomLeft: [0, 0, 255, 255],
      bottomRight: [255, 255, 0, 255],
    };
    for (const [corner, expected] of Object.entries(expectedOverlay)) {
      if (!closeColor(overlay[corner], expected)) throw new Error(`GPU overlay orientation is wrong at ${corner}.`);
    }
    return { plain, persistedIds, maximumLayers, rapidHistory, duplicateUndoRace, overlay };
  });
}
