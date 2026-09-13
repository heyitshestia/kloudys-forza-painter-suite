async (page) => {
  page.setDefaultTimeout(20000);
  const check = (value, message) => { if (!value) throw new Error(message); };
  const idle = () => page.waitForFunction(() => !editorAssetLibrary.busy);
  await page.evaluate(async () => {
    await loadPayload({ shapes: [0, 1, 2].map(index => ({ type: index === 1 ? 1048678 : 1048677, color: [[36, 170, 150, 255], [220, 50, 80, 255], [245, 245, 245, 255]][index], data: [index * 60, 0, .7, .7, 0, 0, 0], editor_group_id: "asset-test-group", editor_group_name: "Reusable badge" })) });
    selectAllLayers();
    activateDockPanel("assetsPane");
  });
  await idle();
  await page.locator("#assetSaveSelection").click();
  await page.locator("#textPromptInput").fill("Reusable badge");
  await page.locator("#textPromptInput").press("Enter");
  await idle();
  check(await page.locator(".editorAsset").count() === 1, "Saving selection must create an asset tile");
  await page.waitForFunction(() => { const img = document.querySelector(".assetPreview img"); return img?.complete && img.naturalWidth > 0; });
  const original = await page.evaluate(() => snapshotShapes());
  for (let i = 0; i < 2; i++) { await page.locator(".assetActions > button").first().click(); await idle(); }
  check(await page.evaluate(() => vinylObjects().length === 9 && new Set(vinylObjects().map(o => o.kloudy.editor_id)).size === 9 && new Set(vinylObjects().map(o => o.kloudy.group_id)).size === 3), "Each insertion needs independent layer/group IDs");
  check(await page.evaluate(original => JSON.stringify(snapshotShapes().slice(0, 3)) === JSON.stringify(original), original), "Inserting must not mutate the source group");
  const beforeUndo = await page.evaluate(() => JSON.stringify(snapshotShapes()));
  await page.evaluate(async () => { await undo(); await redo(); });
  check(await page.evaluate(before => JSON.stringify(snapshotShapes()) === before, beforeUndo), "Asset insertion must undo/redo exactly");
  await page.locator(".editorAsset summary").click();
  await page.getByRole("button", { name: "Rename", exact: true }).click();
  await page.locator("#textPromptInput").fill("Renamed badge");
  await page.locator("#textPromptInput").press("Enter");
  await idle();
  await page.locator("#assetSearch").fill("missing");
  check(await page.locator(".editorAsset").count() === 0, "Search must filter assets");
  await page.locator("#assetSearch").fill("renamed");
  check(await page.locator(".editorAsset").count() === 1, "Search must find renamed asset");
  await page.screenshot({ path: "asset-library.png" });

  await page.evaluate(() => { canvas.discardActiveObject(); canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel(); activateDockPanel("transformPane"); });
  // Locate the real existing pane rather than depending on its tab name.
  await page.evaluate(() => { const pane = document.getElementById("xInput").closest(".dockPane"); if (pane) activateDockPanel(pane.id); });
  const x = page.locator("#xInput");
  await x.fill("(20 + 10) * 2"); await x.press("Enter");
  check(await x.inputValue() === "60", "Enter must apply arithmetic");
  const historyCount = await page.evaluate(() => editorHistory.entries.length);
  await x.press("Tab");
  check(await page.evaluate(() => editorHistory.entries.length) === historyCount, "Blur after Enter must not duplicate history");
  await x.fill("1 / 0"); await x.press("Enter");
  check(await x.getAttribute("aria-invalid") === "true", "Invalid numeric expression must be marked");
  check(await page.evaluate(() => objectToShape(selectedVinylObjects()[0]).data[0]) === 60, "Invalid expression must leave geometry unchanged");
  await x.press("Escape"); check(await x.inputValue() === "60", "Escape must restore the valid value");
  await x.fill("70 + 5"); await x.press("Tab");
  check(await x.inputValue() === "75", "Blur must commit a valid expression");
  const label = await page.locator('[data-numeric-for="xInput"]').boundingBox();
  check(label, "Numeric label must be visible");
  const startHistory = await page.evaluate(() => editorHistory.entries.length);
  await page.mouse.move(label.x + label.width / 2, label.y + label.height / 2);
  await page.mouse.down(); await page.mouse.move(label.x + label.width / 2 + 30, label.y + label.height / 2, { steps: 8 }); await page.mouse.up();
  check(await x.inputValue() === "105", "Label dragging must apply the expected increment");
  check(await page.evaluate(() => editorHistory.entries.length) === startHistory + 1, "Label drag must be one undo step");
  await page.evaluate(() => undo()); check(await x.inputValue() === "75", "Undo must restore the pre-drag transform");
  await page.mouse.move(label.x + 2, label.y + 2); await page.mouse.down(); await page.mouse.move(label.x + 42, label.y + 2, { steps: 4 }); await page.keyboard.press("Escape"); await page.mouse.up();
  check(await x.inputValue() === "75", "Escape must cancel an in-progress label drag");

  await page.evaluate(async () => {
    await loadPayload({ shapes: [0, 1, 2].map(index => ({ type: 1048677, data: [0, 0, 1, 1, 0, 0, 0], color: [40 + index * 70, 150, 160, 255] })) });
    canvas.discardActiveObject();
    document.getElementById("overlapCycle").checked = true;
    document.getElementById("overlapCycle").dispatchEvent(new Event("change"));
  });
  const point = await page.evaluate(() => {
    const object = vinylObjects()[0], p = fabric.util.transformPoint(object.getCenterPoint(), canvas.viewportTransform), bounds = canvas.upperCanvasEl.getBoundingClientRect();
    return { x: bounds.left + p.x, y: bounds.top + p.y };
  });
  const selected = [];
  for (let i = 0; i < 4; i++) { await page.mouse.click(point.x, point.y); selected.push(await page.evaluate(() => selectedVinylObjects()[0]?.kloudy.editor_id)); }
  check(new Set(selected.slice(0, 3)).size === 3 && selected[0] === selected[3], "Overlap clicks must cycle through actual stacked shapes");
  await page.mouse.click(point.x, point.y, { button: "right" });
  check(await page.getByRole("menu", { name: "Overlapping layers" }).isVisible(), "Right click must open overlap menu");
  check(await page.getByRole("menuitem").count() === 3, "Overlap menu must list all hits");
  await page.keyboard.press("End"); await page.keyboard.press("Enter");
  check(await page.getByRole("menuitem").count() === 0, "Selecting a menu entry must close it");
  const geometry = await page.evaluate(() => {
    const circle = new fabric.Circle({ radius: 50, left: 0, top: 0, fill: "#fff", originX: "center", originY: "center" });
    circle.canvas = canvas;
    const center = KfpsFabricAdapter.visiblePixelAt(canvas, circle, new fabric.Point(0, 0));
    const corner = KfpsFabricAdapter.visiblePixelAt(canvas, circle, new fabric.Point(45, 45));
    const ring = new fabric.Circle({ radius: 50, left: 0, top: 0, fill: "transparent", stroke: "#fff", strokeWidth: 8, originX: "center", originY: "center" });
    ring.canvas = canvas;
    const hole = KfpsFabricAdapter.visiblePixelAt(canvas, ring, new fabric.Point(0, 0));
    const edge = KfpsFabricAdapter.visiblePixelAt(canvas, ring, new fabric.Point(49, 0));
    setObjectLocked(vinylObjects()[2], true);
    return { center, corner, hole, edge, unlocked: overlappingVinylObjects(vinylObjects()[0].getCenterPoint()).length };
  });
  check(geometry.center && !geometry.corner && !geometry.hole && geometry.edge && geometry.unlocked === 2, `Pixel hit or lock filtering failed: ${JSON.stringify(geometry)}`);
  const grouped=await page.evaluate(()=> {
    const members=vinylObjects().slice(0,2);
    selectObjects(members,'translated group pixel check');
    const group=canvas.getActiveObject();
    group.set({left:150,top:70,angle:28,scaleX:.8,skewX:15});group.setCoords();
    const point=fabric.util.transformPoint(new fabric.Point(0,0),members[0].calcTransformMatrix());
    return {painted:KfpsFabricAdapter.visiblePixelAt(canvas,members[0],point),hits:overlappingVinylObjects(point).length,
      outside:KfpsFabricAdapter.visiblePixelAt(canvas,members[0],new fabric.Point(20000,20000))};
  });
  check(grouped.painted&&grouped.hits===2&&!grouped.outside,'Transformed group hit bounds used parent-local coordinates: '+JSON.stringify(grouped));
  await page.screenshot({ path: "selection-controls.png" });
  return { assetWorkflow: true, numericWorkflow: true, overlapWorkflow: true, geometry,grouped };
}
