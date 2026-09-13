async page => {
  const result = await page.evaluate(async () => {
    const check = (value, message) => { if (!value) throw new Error(message); };
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, i) => ({
      type: 1048677, color: [50, 140, 210, 255], mask: i > 0 && i % 3 === 0,
      data: [(i % 60) * 24 - 720, Math.floor(i / 60) * 24 - 600, .18, .18, 0, 0, i > 0 && i % 3 === 0 ? 1 : 0],
    })) });
    editorRenderer.endHybridRenderNow();
    fitDesignView();
    const snapshot = JSON.stringify(snapshotShapes());
    const objects = canvas.getObjects;
    let copies = 0;
    canvas.getObjects = function (...args) { copies++; return objects.apply(this, args); };
    for (let i = 0; i < 5; i++) syncMaskPreviewOutlines();
    canvas.getObjects = objects;
    check(copies < 50, `Mask helper maintenance copied the whole stack ${copies} times`);
    const owner = vinylObjects()[3], helper = maskPreviewOutlines.get(owner);
    let coords = 0;
    const setCoords = helper.setCoords;
    helper.setCoords = function (...args) { coords++; return setCoords.apply(this, args); };
    syncMaskHelperTransform(owner, helper);
    const initialCoords = coords;
    for (let i = 0; i < 20; i++) syncMaskHelperTransform(owner, helper);
    check(coords === initialCoords, "Unchanged mask helpers recomputed coordinates");
    owner.left += 9;
    syncMaskHelperTransform(owner, helper);
    check(helper.left === owner.left && coords > initialCoords, "Changed mask helper was not updated");
    const beforePan = coords;
    canvas.viewportTransform[4] += 20;
    syncMaskHelperTransform(owner, helper);
    check(coords > beforePan, "In-place viewport mutation left stale mask coordinates");
    owner.left -= 9;
    canvas.viewportTransform[4] -= 20;
    syncMaskHelperTransform(owner, helper);
    helper.setCoords = setCoords;
    check(JSON.stringify(snapshotShapes()) === snapshot, "Helper maintenance altered artwork");
    const layer = vinylObjects()[1], render = layer.render;
    let draws = 0;
    layer.render = function (...args) { draws++; return render.apply(this, args); };
    canvas.renderAll();
    check(draws > 0, "Fabric baseline did not render the fixture");
    draws = 0;
    check(editorRenderer.beginHybridRender("render gate regression"), "GPU preview unavailable");
    // The normal scene stays available until a successful preview is presented.
    // Calling the draw helper alone intentionally does not hide that fallback.
    await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    check(editorRenderer.active && canvas.lowerCanvasEl.style.visibility==='hidden', "GPU preview was not presented");
    draws=0;
    canvas.renderAll();
    check(draws === 0, "Hidden Fabric scene was rendered during GPU preview");
    const surface = document.createElement("canvas");
    surface.width = surface.height = 64;
    canvas._renderObjects(surface.getContext("2d"), [layer]);
    check(draws > 0, "Render gate incorrectly blocked a separate export context");
    draws = 0;
    editorRenderer.endHybridRenderNow();
    canvas.renderAll();
    check(draws > 0 && canvas.lowerCanvasEl.style.visibility !== "hidden", "Fabric fallback was not restored");
    layer.render = render;
    const leading = exportValidation([vinylObjects()[3], vinylObjects()[6], vinylObjects()[0], vinylObjects()[9]]);
    check(leading.warnings.some(issue => issue.message.includes("2 mask")), "Mask ordering validation changed");
    canvas.discardActiveObject();
    const first = vinylObjects()[0], second = vinylObjects()[1];
    canvas.setActiveObject(first); nudgeSelected(2, 0);
    canvas.setActiveObject(second); nudgeSelected(3, 0);
    const convert = window.objectToShape;
    let conversions = 0;
    window.objectToShape = function (...args) { conversions++; return convert.apply(this, args); };
    // UI validation still checks all layers; count the history capture separately.
    const validate = window.refreshExportValidation;
    window.refreshExportValidation = () => {};
    flushPendingNudgeHistory();
    window.refreshExportValidation = validate;
    window.objectToShape = convert;
    check(conversions === 2, `Nudge history converted ${conversions} objects, expected both edited leaves`);
    check(JSON.stringify(currentHistoryState().shapes) === JSON.stringify(snapshotShapes()), "Nudge capture omitted a changed layer");
    const moved = JSON.stringify(snapshotShapes());
    await undo();
    check(JSON.stringify(snapshotShapes()) === snapshot, "Nudge undo changed untouched layers");
    await redo();
    check(JSON.stringify(snapshotShapes()) === moved, "Nudge redo failed");
    canvas.discardActiveObject();
    canvas.setActiveObject(vinylObjects().at(-2));
    window.pipelineEntriesBefore = layerListEntries;
    const target = canvas.getActiveObject();
    target.left += 5; target.setCoords();
    canvas.fire("object:modified", { target });
    return { stackCopies: copies, maskCoordinateInvalidation: true, hiddenSceneSkipped: true, exportContextPreserved: true, fallbackRestored: true, nudgeConversions: conversions, undoRedo: true };
  });
  await page.waitForTimeout(300);
  const geometryOnly = await page.evaluate(() => {
    if (layerListEntries !== window.pipelineEntriesBefore) throw new Error("A geometry-only edit rebuilt every layer entry");
    const target = selectedVinylObjects()[0];
    const entry = renderedLayerEntries.find(entry => entry.object === target);
    if (!entry?.element?.textContent.includes(`X ${round(fh6DataFromObject(target)[0])}`)) throw new Error("Visible layer coordinates were not refreshed");
    return true;
  });
  await page.evaluate(() => {
    window.pipelineEntriesBefore = layerListEntries;
    scheduleRefreshLayers({ geometryOnly: true });
    scheduleRefreshLayers();
    scheduleRefreshLayers({ geometryOnly: true });
  });
  await page.waitForTimeout(100);
  const structureWins = await page.evaluate(() => layerListEntries !== window.pipelineEntriesBefore);
  if (!structureWins) throw new Error("A geometry-only request suppressed a queued structural refresh");
  await page.screenshot({ path: "pipeline-native.png" });
  return { ...result, geometryOnly, structureWins };
}
