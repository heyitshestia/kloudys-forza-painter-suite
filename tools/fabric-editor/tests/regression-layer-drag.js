async (page) => {
  page.setDefaultTimeout(180000);
  await page.evaluate(async () => {
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
    activateDockPanel("layersPane");
    const viewport = document.getElementById("layersViewport");
    viewport.scrollTop = 0;
    renderVirtualLayerWindow(true);
    window.__layerDragBefore = vinylObjects().map((object) => object.kloudy.editor_id);
  });

  const rows = page.locator("#layers > li");
  const source = await rows.nth(0).boundingBox();
  const target = await rows.nth(3).boundingBox();
  if (!source || !target) throw new Error("Virtual layer rows were not available for drag testing.");
  await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
  await page.mouse.down();
  await page.mouse.move(target.x + target.width / 2, target.y + target.height / 2 + 4, { steps: 8 });
  await page.mouse.up();

  return page.evaluate(() => {
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
    if (result.layers !== 3000 || result.uniqueLayers !== 3000) throw new Error("Layer drag lost or duplicated layers.");
    if (!result.orderChanged || result.sourceMovedBy === 0) throw new Error("Pointer drag did not change stack order.");
    if (!result.dragStateCleared) throw new Error("Layer drag state was not cleaned up after pointer release.");
    return result;
  });
}
