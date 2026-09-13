async (page) => {
  page.setDefaultTimeout(300000);
  const result = await page.evaluate(async () => {
    // Frozen native IDs from the saved-file / in-game validation, not the resolver.
    const tabs = [
      ["Primitives", 101],
      ["Community_Vinyls_1", 2101], ["Community_Vinyls_2", 2201],
      ["Community_Vinyls_3", 2301], ["Community_Vinyls_4", 2401],
      ["Gradient_Shapes", 201], ["Stripes", 301], ["Tears", 401],
      ["Racing_Icons", 501], ["Flames", 601], ["Paint_Splats", 701],
      ["Tribal", 801], ["Nature", 901],
      ["Upper_Letters_1", 1901], ["Lower_Letters_1", 2001],
      ["Upper_Letters_2", 1301], ["Lower_Letters_2", 1401],
      ["Upper_Letters_3", 1501], ["Lower_Letters_3", 1601],
      ["Upper_Letters_4", 1701], ["Lower_Letters_4", 1801],
      ["Upper_Letters_5", 2501], ["Lower_Letters_5", 2601],
      ["Upper_Letters_6", 2701], ["Lower_Letters_6", 2801],
      ["Upper_Letters_7", 2901], ["Lower_Letters_7", 3001],
      ["Upper_Letters_8", 3101], ["Lower_Letters_8", 3201],
      ["Upper_Letters_9", 3301], ["Lower_Letters_9", 3401],
      ["Upper_Letters_10", 3501], ["Lower_Letters_10", 3601],
      ["Upper_Letters_11", 3701], ["Lower_Letters_11", 3801],
    ];
    const check = (shape, family, index, word, stage) => {
      if (shape.type !== 0x100000 + word || shape.type_word !== word
          || shape.resource_family !== family || shape.resource_index !== index) {
        throw new Error(`${stage}: ${family}:${index} expected word ${word}: ${JSON.stringify(shape)}`);
      }
    };
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
    $("shapePlacementMode").value = "top";
    const completed = [];
    for (const [family, base] of tabs) {
      clearVinylObjects();
      resetHistory();
      currentProjectName = `Identity-${family}`;
      for (let index = 1; index <= 40; index += 1) {
        await addShape(family, index);
        const object = canvas.getActiveObject();
        object.set({ left: ((index - 1) % 10) * 90 - 405,
          top: Math.floor((index - 1) / 10) * 100 - 150,
          scaleX: 0.4, scaleY: 0.4 });
        check(objectToShape(object), family, index, base + index - 1, "add");
        if (!object.kloudy.mesh_path || !object.width || !object.height) {
          throw new Error(`Missing native mesh: ${family}:${index}`);
        }
      }
      canvas.discardActiveObject();
      const expected = snapshotShapes();
      await exportJson();
      if (String($("status")?.textContent || "").includes("failed")) {
        throw new Error(`Export failed for ${family}`);
      }
      // Disk readback and project rehydration use the normal server APIs.
      const saved = await saveProjectToAppFolder(currentProjectName,
        editableProjectPayload(currentProjectName), true);
      const response = await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(saved.id)}`);
      if (!response.ok) throw new Error(`Project readback failed: ${family}`);
      const readback = await response.json();
      await loadProjectPayload(readback.payload, currentProjectName);
      snapshotShapes().forEach((shape, offset) => {
        check(shape, family, offset + 1, base + offset, "project reopen");
        if (shape.editor_id !== expected[offset].editor_id) throw new Error("Changed editor ID");
      });
      completed.push(family);
    }

    clearVinylObjects();
    resetHistory();
    await addShape("Primitives", 21);
    const replacements = await replaceObjectsWithResource(vinylObjects(), "Primitives", 29);
    check(objectToShape(replacements[0]), "Primitives", 29, 129, "replace 21 with 29");
    await loadPayload({ shapes: [{ type: 0x100000 + 129, type_word: 121,
      resource_family: "Primitives", resource_index: 21,
      data: [0, 0, 1, 1, 0, 0, 0], color: [255, 255, 255, 255] }] });
    check(objectToShape(vinylObjects()[0]), "Primitives", 29, 129, "conflicting old JSON");
    currentProjectName = "Identity-conflict-normalized";
    await exportJson();
    return { tabs: completed.length, addedShapes: completed.length * 40,
      projectReopenedShapes: completed.length * 40,
      replacementWord: 129, conflictingInputNormalizedWord: 129 };
  });
  await page.evaluate(() => {
    clearVinylObjects();
    resetHistory();
    currentProjectName = "Identity-tile-clicks";
    $("shapeSearch").value = "";
    showFavoritesOnly = false;
    activateDockPanel("shapeLibraryPane");
  });
  const clicked = [
    ["Primitives", 29, 129], ["Primitives", 21, 121],
    ["Primitives", 35, 135], ["Primitives", 3, 103],
    ["Community_Vinyls_1", 3, 2103], ["Community_Vinyls_1", 8, 2108],
    ["Community_Vinyls_1", 17, 2117],
  ];
  for (const [family, index, word] of clicked) {
    await page.locator("#shapeFamily").selectOption(family);
    await page.locator("#shapeGrid .shapeTile").nth(index - 1).click();
    await page.waitForFunction((expected) => canvas.getActiveObject()?.kloudy?.type_word === expected, word);
  }
  const savedResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/fabric-editor/save-editor-json")
    && response.request().method() === "POST");
  await page.locator("#exportJson").click();
  const response = await savedResponse;
  if (!response.ok()) throw new Error(`Export button HTTP ${response.status()}`);
  const saved = await response.json();
  const words = await page.evaluate(async (id) => {
    const response = await fetch(`${JSON_FILE_API}?id=${encodeURIComponent(id)}`);
    if (!response.ok) throw new Error("Export button disk readback failed");
    const readback = await response.json();
    return readback.payload.shapes.map((shape) => shape.type_word);
  }, saved.id);
  if (JSON.stringify(words) !== JSON.stringify(clicked.map((entry) => entry[2]))) {
    throw new Error(`Shape-tile / export-button identity mismatch: ${JSON.stringify(words)}`);
  }
  return { ...result, tileClickExportWords: words };
}
