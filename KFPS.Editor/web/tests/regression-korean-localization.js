async (page) => {
  // Run against a Korean editor instance with a writable, disposable asset library.
  page.setDefaultTimeout(25000);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const idle = () => page.waitForFunction(() => !editorAssetLibrary.busy);
  const initial = await page.evaluate(async () => {
    if (KfpsI18n.language !== "ko") throw new Error("This regression requires Korean UI.");
    const family = [...document.querySelector("#shapeFamily").options].find(option => option.value === "Primitives");
    const shapes = ["Save", "테스트 {1} <&>"].map((name, index) => ({
      type: 1048677, type_word: 101, resource_family: "Primitives", resource_index: 1,
      shape_name: name, editor_id: `ko-regression-${index}`, editor_group_id: "ko-test-group",
      editor_group_name: "My Group {0}", data: [index * 80, 0, 0.7, 0.7, 0, 0, 0], color: [60, 160, 210, 255],
    }));
    await loadPayload({ shapes });
    const serialized = snapshotShapes();
    canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel();
    const beforeIme = vinylObjects().length;
    document.dispatchEvent(new KeyboardEvent("keydown", {key:"Delete", isComposing:true, bubbles:true}));
    const imeProtected = vinylObjects().length === beforeIme;
    setStatus(KfpsI18n.t("Recovery pending"));
    reportAutosaveResult({ recovery_revision: editorRecovery.revision }, true, true, null);
    return {
      lang: document.documentElement.lang, title: document.title,
      family: family?.textContent, value: family?.value,
      shapeName: editorCatalog.shapeDisplayName("Primitives", 1), displayName: localizedShapeDisplayName("Primitives", 1),
      search: shapeSearchText("Primitives", 1, 1048677),
      names: serialized.map(shape => shape.shape_name), groups: serialized.map(shape => shape.editor_group_name),
      sourceIds: serialized.map(shape => [shape.resource_family, shape.resource_index, shape.type_word]),
      imeProtected, recovery: document.getElementById("status").textContent,
    };
  });
  check(initial.lang === "ko" && /편집기/.test(initial.title), "Document language/title not localized");
  check(initial.family === "기본 도형" && initial.value === "Primitives", "Family value must remain original");
  check(initial.shapeName === "Square" && initial.displayName === "정사각형", "Resource name must remain original internally");
  check(initial.search.includes("square") && initial.search.includes("정사각형"), "Bilingual shape search missing");
  check(JSON.stringify(initial.names) === JSON.stringify(["Save", "테스트 {1} <&>"]), "User names altered");
  check(initial.groups.every(name => name === "My Group {0}"), "Group names altered");
  check(initial.sourceIds.every(row => row[0] === "Primitives" && row[1] === 1 && row[2] === 101), "Shape identifiers altered");
  check(initial.imeProtected, "IME composition activated a destructive shortcut");
  check(initial.recovery.includes("KFPS") && !initial.recovery.includes("Recovery"), "Korean recovery status not updated");

  const tools = await page.evaluate(() => {
    const labels = [];
    for (const button of document.querySelectorAll(".toolButton[data-tool]")) {
      setToolRailMode(button.dataset.toolMode, button.dataset.tool);
      labels.push(document.getElementById("activeToolLabel").textContent);
    }
    setToolRailMode("select");
    return labels;
  });
  check(tools.every(label => /[가-힣]/.test(label)), "Active tool caption not translated");

  // The unstaged asset-library changes must still work in the localized build.
  await page.evaluate(() => { selectAllLayers(); activateDockPanel("assetsPane"); });
  await idle();
  await page.locator("#assetSaveSelection").click();
  check(/[가-힣]/.test(await page.locator("#textPromptTitle").innerText()), "Asset prompt not localized");
  await page.locator("#textPromptInput").fill("Save {0} 한국어 에셋");
  await page.locator("#textPromptInput").press("Enter");
  await idle();
  await page.locator("#assetSearch").fill("Save {0} 한국어 에셋");
  const card = page.locator(".editorAsset").filter({has: page.locator("strong", {hasText: "Save {0} 한국어 에셋"})});
  check(await card.count() === 1, "Asset save/name preservation failed");
  const before = await page.evaluate(() => snapshotShapes());
  await card.locator(".assetActions > button").click();
  await idle();
  check(await page.evaluate(() => vinylObjects().length) === 4, "Localized asset insertion failed");
  check(await page.evaluate(prior => JSON.stringify(snapshotShapes().slice(0, 2)) === JSON.stringify(prior), before), "Asset insertion altered originals");
  await card.locator("summary").click();
  await card.getByRole("button", {name: "이름 변경", exact: true}).click();
  await page.locator("#textPromptInput").fill("Renamed {1} 한국어");
  await page.locator("#textPromptInput").press("Enter");
  await idle();
  await page.locator("#assetSearch").fill("Renamed {1} 한국어");
  check((await page.locator("#assetGrid").innerText()).includes("Renamed {1} 한국어"), "Asset rename failed");

  // New arithmetic input handling must retain the original validation/geometry.
  await page.evaluate(() => {
    canvas.discardActiveObject(); canvas.setActiveObject(vinylObjects()[0]); updateSelectionPanel();
    activateDockPanel(document.getElementById("xInput").closest(".dockPane").id);
  });
  const x = page.locator("#xInput");
  await x.fill("(20 + 10) * 2"); await x.press("Enter");
  check(await x.inputValue() === "60", "Arithmetic input failed");
  await x.fill("1 / 0"); await x.press("Enter");
  check(await x.getAttribute("aria-invalid") === "true", "Invalid expression not marked");
  check((await page.locator("#status").innerText()).includes("0으로 나눌 수 없습니다"), "Numeric validation not Korean");
  check(await page.evaluate(() => objectToShape(selectedVinylObjects()[0]).data[0]) === 60, "Invalid expression changed geometry");
  await x.press("Escape");

  // Check the complete inline help and every guided-tour step.
  await page.locator("#helpBtn").click();
  check((await page.locator("#helpDialog").innerText()).includes("첫 프로젝트 작업 순서"), "Full help block missing");
  await page.evaluate(() => document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close()));
  const tour = await page.evaluate(() => {
    startEditorTour();
    const steps = [];
    for (let i = 0; i < EDITOR_TOUR_STEPS.length; i++) {
      showTourStep(i);
      steps.push({title: document.getElementById("editorTourTitle").textContent, body: document.getElementById("editorTourBody").textContent});
    }
    stopEditorTour(false);
    return steps;
  });
  check(tour.every(step => /[가-힣]/.test(step.title) && /[가-힣]/.test(step.body)), "Tour step untranslated");
  check(tour.every(step => !/\{\d+\}/.test(step.title + step.body)), "Unformatted tour placeholder");

  // Selecting another language must not reload or discard the open document.
  const beforeLanguage = await page.evaluate(() => JSON.stringify(snapshotShapes()));
  await page.locator("#editorLanguageSelect").selectOption("en");
  await page.waitForFunction(() => !document.getElementById("editorLanguageSelect").disabled);
  const afterLanguage = await page.evaluate(() => ({
    selected: editorSettings.getItem(KfpsI18n.KEY), active: KfpsI18n.language,
    shapes: JSON.stringify(snapshotShapes()), dialog: [...document.querySelectorAll("dialog[open]")].map(d => d.textContent).join(" "),
  }));
  check(afterLanguage.selected === "en" && afterLanguage.active === "ko", "Language selection did not persist for restart");
  check(afterLanguage.shapes === beforeLanguage, "Language switch changed current document");
  check(/[가-힣]/.test(afterLanguage.dialog), "Language restart notice missing");
  // Leave this test's original language preference in place for other tests.
  await page.evaluate(async () => { editorSettings.setItem(KfpsI18n.KEY, "ko"); await KfpsEditorPreferences.flush(); });
  return {staticUi:true, bilingualSearch:true, opaqueUserNames:true, resourceIds:true, ime:true,
    recovery:true, assetSaveInsertRename:true, numericValidation:true, help:true, tourSteps:tour.length, safeLanguageSwitch:true};
}
