async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  page.setDefaultTimeout(15000);
  const initial = await h.setup(page, output, options);
  const initiallyEnabled = await page.locator("#selectAllLayers").isEnabled();
  await h.selectId(page, h.input(options).project.shapes.at(-1).editor_id);
  const read = () => page.evaluate(() => ({ shapes: snapshotShapes(), matrices: vinylObjects().map(o => o.calcTransformMatrix()),
    flips: vinylObjects().map(o => ({ id: o.kloudy.editor_id, x: o.flipX, y: o.flipY, angle: o.angle,
      scaleX: o.scaleX, scaleY: o.scaleY, group: o.group?.type || null })),
    selected: selectedVinylObjects().length, history: editorHistory.index, dirty: documentDirty }));
  const original = await read(), stages = [];
  for (const button of ["selectAllLayers", "clearLayerSelection", "selectAllLayers", "clearLayerSelection"]) {
    await page.locator(`#${button}`).click();
    const state = await read();
    const differences = state.shapes.map((shape, index) => ({ index, id: shape.editor_id,
      before: original.shapes[index].data, after: shape.data,
      beforeFabric: original.flips[index], afterFabric: state.flips[index],
      matrixError: Math.max(...state.matrices[index].map((value, j) => Math.abs(value - original.matrices[index][j]))) }))
      .filter((item, index) => JSON.stringify(state.shapes[index]) !== JSON.stringify(original.shapes[index]));
    stages.push({ button, selected: state.selected, history: state.history, dirty: state.dirty, differences });
    fs.writeFileSync(path.join(output, "selection-invariance.json"), JSON.stringify({ initial, initiallyEnabled, stages }, null, 2));
  }
  await page.locator("#saveProject").click();
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  h.check(stages.every(stage => stage.differences.length === 0), "Selection-only operations changed saved shape transforms");
  h.check(initiallyEnabled, "Select All remained disabled after loading the handmade project");
  return { initial, stages, selectionDoesNotEditArtwork: true };
}
