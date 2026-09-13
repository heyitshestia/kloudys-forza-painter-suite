async (page,options={}) => {
  const h=require(path.join(__dirname,'dense-human-fixture.cjs'));
  page.setDefaultTimeout(30000);
  const handmade=options.project ? await require(path.join(__dirname,'handmade-project-fixture.cjs')).setup(page,output,options) : null;
  if(!handmade)await page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [80 + index % 160, 140, 220, 255],
      data: [-850 + (index % 60) * 28, 620 - Math.floor(index / 60) * 25, 0.2, 0.2, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    await loadPayload({ shapes });
  });
  await page.locator('#layersPane').waitFor({state:'visible'});
  await page.evaluate(async () => {
    const viewport = document.getElementById("layersViewport");
    viewport.scrollTop = 0;
    renderVirtualLayerWindow(true);
    window.__layerDragBefore = vinylObjects().map((object) => object.kloudy.editor_id);
    window.__layerDragShapes = JSON.stringify(snapshotShapes());
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
  if(options.reference && !handmade) {
    await h.fileInput(page,'#overlayInput',options.reference);
    await page.waitForFunction(()=>!!editorReference.image&&!recoveryRestoreDepth);
  }
  await page.locator('#fitView').click();
  const initial=await h.scene(page);
  const expectedCount=handmade ? handmade.layers : 3000;
  if(initial.visible<expectedCount*.9)throw Error('Layer drag fixture was not densely visible');

  const rows = page.locator("#layers > li");
  const source = await rows.nth(0).boundingBox();
  const viewport = await page.locator("#layersViewport").boundingBox();
  const target = await rows.nth(3).boundingBox();
  if (!source || !target || !viewport) throw new Error("Virtual layer rows were not available for drag testing.");
  const x = viewport.x + viewport.width / 2;
  const y = Math.min(target.y + target.height / 2 + 4, viewport.y + viewport.height - 10);
  await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
  await page.mouse.down();
  await page.mouse.move(x, y, { steps: 12 });
  if (target.y + target.height / 2 + 4 > viewport.y + viewport.height) {
    await page.mouse.wheel(0, 180);
    await page.waitForTimeout(150);
    await page.mouse.move(x + 2, y - 2, { steps: 3 });
  }
  await page.mouse.up();

  const result=await page.evaluate(expectedCount => {
    const before = window.__layerDragBefore;
    const after = vinylObjects().map((object) => object.kloudy.editor_id);
    const sourceId = before[before.length - 1];
    const movedBy = after.indexOf(sourceId) - before.indexOf(sourceId);
    const result = {
      layers: after.length,
      uniqueLayers: new Set(after).size,
      orderChanged: after.some((id, index) => id !== before[index]),
      sourceMovedBy: movedBy,
      mountedRows: document.querySelectorAll("#layers > li").length,
      dragStateCleared: layerDragState === null && !document.body.classList.contains("layerReorderActive"),
    };
    if (result.layers !== expectedCount || result.uniqueLayers !== expectedCount) throw new Error("Layer drag lost or duplicated layers.");
    if (!result.orderChanged || result.sourceMovedBy === 0) throw new Error("Pointer drag did not change stack order.");
    if (!result.dragStateCleared) throw new Error("Layer drag state was not cleaned up after pointer release.");
    return result;
  },expectedCount);
  await page.locator('#undoBtn').click();await page.waitForFunction(()=>!editorCommands.busy);
  if(!await page.evaluate(()=>JSON.stringify(snapshotShapes())===__layerDragShapes))throw Error('Dense row drag failed exact undo');
  if(handmade)await require(path.join(__dirname,'handmade-project-fixture.cjs')).saveAs(page,'Layer order checkpoint');
  return {...result,initial,exactUndo:true};
}
