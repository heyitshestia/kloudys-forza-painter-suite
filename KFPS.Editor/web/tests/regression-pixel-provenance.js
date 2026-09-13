async page => page.evaluate(async () => {
  const assert = (ok, message) => { if (!ok) throw Error(message); };
  const checks = [];
  const shapes = Array.from({ length: 2400 }, (_, i) => ({ type: 1048677,
    color: [60, 100, 140, 255], data: [(i % 60) * 9, Math.floor(i / 60) * 9, .05, .05, 0, 0, 0] }));
  await loadProjectPayload({ shapes, name: "Pixel provenance" });
  const bitmap = document.createElement("canvas"); bitmap.width = bitmap.height = 4;
  const context = bitmap.getContext("2d"); context.fillStyle = "#ed6c90"; context.fillRect(0, 0, 4, 4);
  pixelArtSourceFile = new File([await new Promise(resolve => bitmap.toBlob(resolve))], "Pixel.png", { type: "image/png" });
  await generatePixelArtRectangles();
  const generated = vinylObjects().filter(object => object.kloudy.pixel_art_generated);
  assert(generated.length > 0, "Real pixel generation did not create replacement targets");
  const count = generated.length;
  pushHistory("pixel fixture");
  await saveProject();
  const receipt = editorProjects.association;
  const saved = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(receipt.target_id)}`);
  assert(saved.payload.shapes.filter(shape => shape.editor_pixel_art_generated === true).length === count, "Disk lost provenance");
  await loadProjectPayload(saved.payload, "Pixel provenance", { receipt: saved.receipt });
  assert(vinylObjects().filter(object => object.kloudy.pixel_art_generated).length === count, "Reopen lost provenance");
  checks.push("real generation -> disk -> reopen");
  const target = vinylObjects().find(object => object.kloudy.pixel_art_generated);
  canvas.setActiveObject(target); await duplicateSelected();
  assert(vinylObjects().filter(object => object.kloudy.pixel_art_generated).length === count, "Duplicate inherited replacement eligibility");
  await insertCopiedShapesNow([objectToShape(target)], { asset: true });
  assert(vinylObjects().filter(object => object.kloudy.pixel_art_generated).length === count, "Independent asset inherited replacement eligibility");
  checks.push("duplicates and independent asset insertion remain independent");
  canvas.setActiveObject(target); deleteSelected(); await undo();
  assert(vinylObjects().filter(object => object.kloudy.pixel_art_generated).length === count, "Undo reconstruction lost provenance");
  const recovery = autosavePayloadFromState(currentHistoryState());
  await recoverAutosavePayload(recovery);
  assert(vinylObjects().filter(object => object.kloudy.pixel_art_generated).length === count, "Recovery lost provenance");
  const handMade = vinylObjects().filter(object => !object.kloudy.pixel_art_generated).map(object => objectToShape(object));
  await generatePixelArtRectangles();
  assert(vinylObjects().filter(object => object.kloudy.pixel_art_generated).length === count, "Clear previous did not replace generated shapes");
  assert(JSON.stringify(vinylObjects().filter(object => !object.kloudy.pixel_art_generated).map(object => objectToShape(object))) === JSON.stringify(handMade),
    "Clear previous changed independent artwork");
  checks.push("delete/undo, recovery, repeat generation, exact independent artwork");
  const object = vinylObjects()[0], original = objectToShape(object);
  applyHistoryShapeToObject(object, { ...original, editor_pixel_art_generated: true });
  assert(object.kloudy.pixel_art_generated === true, "In-place history did not set provenance");
  applyHistoryShapeToObject(object, original);
  assert(object.kloudy.pixel_art_generated === false, "In-place history did not clear missing provenance");
  assert(!Object.hasOwn(objectToShape(vinylObjects().find(item => item.kloudy.pixel_art_generated), { includeEditorMeta: false }), "editor_pixel_art_generated"), "Game export contains editor provenance");
  checks.push("in-place metadata transitions and clean game export");
  await clearAutosave(); documentDirty = false;
  return { passed: true, checks, visibleShapes: vinylObjects().length };
})
