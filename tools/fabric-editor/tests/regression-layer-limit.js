async (page) => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const makeShapes = (count) => Array.from({ length: count }, (_value, index) => ({
      type: 1048677,
      type_word: 101,
      resource_family: "Primitives",
      resource_index: 1,
      color: [180, 110, 210, 255],
      data: [(index % 60) * 20, -Math.floor(index / 60) * 20, 0.16, 0.16, 0, 0, 0],
    }));
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    await loadPayload({ shapes: makeShapes(3000) });
    const before = vinylObjects().length;
    canvas.setActiveObject(vinylObjects()[0]);
    await duplicateSelected();
    const afterDuplicate = vinylObjects().length;
    let overLimitError = "";
    try {
      await loadPayload({ shapes: makeShapes(3001) });
    } catch (error) {
      overLimitError = error.message || String(error);
    }
    const sentinelShapes = makeShapes(3001);
    sentinelShapes[0] = {
      type: 1,
      color: [0, 0, 0, 0],
      data: [0, 0, 1, 1, 0],
    };
    await loadPayload({ shapes: sentinelShapes });
    return {
      before,
      afterDuplicate,
      validSentinelImportLayers: vinylObjects().length,
      overLimitRejected: overLimitError.includes("3000"),
      remainingCapacity: remainingLayerCapacity(),
    };
  });
}
