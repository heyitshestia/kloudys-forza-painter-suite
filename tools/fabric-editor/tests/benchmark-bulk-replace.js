async (page) => {
  page.setDefaultTimeout(300000);
  return page.evaluate(async () => {
    const shapes = Array.from({ length: 3000 }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [80 + index % 150, 140, 210, 255],
      data: [-800 + (index % 60) * 27, 600 - Math.floor(index / 60) * 24, 0.2, 0.2, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    await loadPayload({ shapes });
    const idsBefore = vinylObjects().map((object) => object.kloudy.editor_id);
    const started = performance.now();
    const replacements = await replaceObjectsWithResource(vinylObjects(), "Primitives", 2);
    const replaceMs = performance.now() - started;
    const objects = vinylObjects();
    return {
      layers: objects.length,
      replacements: replacements.length,
      replaceMs,
      idsPreserved: objects.every((object, index) => object.kloudy.editor_id === idsBefore[index]),
      orderPreserved: objects.every((object, index) => object === replacements[index]),
      allResourcesChanged: objects.every((object) => object.kloudy.resource_family === "Primitives" && object.kloudy.resource_index === 2),
      mountedLayerDescendants: document.querySelectorAll("#layers *").length,
    };
  });
}
