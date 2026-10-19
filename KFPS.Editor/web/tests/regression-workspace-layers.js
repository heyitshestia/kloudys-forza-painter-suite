async (page) => {
  const fixture = require(path.join(__dirname, "dense-human-fixture.cjs"));
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  // Focused product-path check without repeating the verified dense UI matrix.
  const exportOnly = process.env.KFPS_WORKSPACE_LAYERS_EXPORT_ONLY === "1";
  const layerCount = exportOnly ? 12 : 3000;
  page.setDefaultTimeout(120000);
  await page.setViewportSize({ width: 1600, height: 1000 });
  const shapes = Array.from({ length: layerCount }, (_, index) => ({
    type: [1048677, 1048678, 1048679][index % 3],
    color: [60 + index % 160, 145, 210, 255],
    data: [-850 + index % 60 * 28, 620 - Math.floor(index / 60) * 25, .18, .18, index % 4 * 15, 0, 0],
    editor_id: `workspace-layer-${index}`,
    shape_name: index === layerCount - 1 ? `Layer ${index} <test> & "name"` : `Layer ${index}`,
    ...(index < 3 ? { editor_group_id: "workspace-layer-group", editor_group_name: 'Group <test> & "name"',
      editor_hidden: index === 0, editor_locked: index === 1 } : {}),
  }));
  const input = path.join(output, "workspace-layers-input.json");
  fs.writeFileSync(input, JSON.stringify({ shapes }));
  const beforeImport = await page.evaluate(() => documentIdentity);
  await fixture.fileInput(page, "#jsonInput", input);
  await page.waitForFunction(({ previous, count }) => documentIdentity > previous && vinylObjects().length === count
    && document.getElementById("busyBanner").hidden && !recoveryRestoreDepth,
  { previous: beforeImport, count: layerCount });
  await page.evaluate(() => { activateDockPanel("layersPane"); refreshLayers(); });
  const snapshot = () => page.evaluate(() => JSON.stringify(vinylObjects().map(object => objectToShape(object, { includeEditorMeta: true }))));
  const original = await snapshot();
  let presentation = null, rowRenderCalls = null;
  if (!exportOnly) {
    const initialHistory = await page.evaluate(() => editorHistory.entries.length);
    const rows = page.locator("#layers .layerRow");
    const first = rows.first();
    // Fail early on focus/scroll coupling before the longer mutation round trips.
    await page.evaluate(() => { const pane = layerScrollPane(); pane.scrollTop = pane.scrollHeight; renderVirtualLayerWindow(true); });
    const boundaryGroup = page.locator("#layers .layerGroupRow");
    await boundaryGroup.locator(".layerGroupTwist").focus();
    await boundaryGroup.locator(".layerGroupTwist").press("Enter");
    check(await boundaryGroup.getAttribute("aria-expanded") === "false", "Initial boundary collapse failed");
    await page.keyboard.press("Enter");
    check(await boundaryGroup.getAttribute("aria-expanded") === "true", "Initial boundary expand lost keyboard focus");
    await page.evaluate(() => { layerScrollPane().scrollTop = 0; renderVirtualLayerWindow(true); });
    console.log("workspace-layers: initial virtual boundary focus passed");
    await page.waitForFunction(() => [...document.querySelectorAll("#layers .layerRow")].slice(0, 3)
      .every(row => { const image = row.querySelector(".layerThumbnail img"); return image?.complete && image.naturalWidth > 0; }));
    presentation = await page.evaluate(() => {
      const rows = [...document.querySelectorAll("#layers [data-layer-list-key]")];
      const first = rows[0];
      return {
        mounted: rows.length, total: layerListEntries.length,
        stride: rows[1].getBoundingClientRect().top - first.getBoundingClientRect().top,
        named: first.querySelector(".layerMain b").textContent.includes('Layer 2999 <test> & "name"'),
        escaped: !first.querySelector("test"), role: first.getAttribute("role"),
        selected: first.getAttribute("aria-selected"), focusable: first.tabIndex === 0,
        previews: rows.slice(0, 3).map(row => row.querySelector(".layerThumbnail img").getAttribute("src")),
        visibility: first.querySelector(".layerVisibility").getAttribute("aria-pressed"),
        locked: first.querySelector(".layerLock").getAttribute("aria-pressed"),
        labels: [...first.querySelectorAll("button")].every(button => button.dataset.workspaceTooltip && button.getAttribute("aria-label")),
        iconsAvailable: typeof window.KfpsWorkspace?.icon === "function",
        iconCount: first.querySelectorAll(".layerIcon svg").length,
      };
    });
    check(presentation.total === 3001 && presentation.mounted < 45, "Dense list lost virtualization");
    check(Math.abs(presentation.stride - 62) < .5, "Layer stride must remain 62px");
    check(presentation.named && presentation.escaped && presentation.focusable && presentation.labels, "Layer name or accessible controls missing");
    check(presentation.role === "treeitem" && presentation.selected === "false", "Initial row selection semantics missing");
    check(presentation.visibility === "true" && presentation.locked === "false", "Initial visibility/lock state is wrong");
    check(new Set(presentation.previews).size === 3, "Different native shapes reused the same thumbnail");
    if (presentation.iconsAvailable) check(presentation.iconCount === 2, "Workspace eye/lock icons missing");

    rowRenderCalls = await page.evaluate(() => {
      let calls = 0;
      const objects = vinylObjects(), originals = objects.map(object => Object.getOwnPropertyDescriptor(object, "render"));
      try {
        objects.forEach(object => { object.render = () => { calls++; }; });
        renderVirtualLayerWindow(true);
      } finally {
        objects.forEach((object, index) => {
          if (originals[index]) Object.defineProperty(object, "render", originals[index]);
          else delete object.render;
        });
      }
      return calls;
    });
    check(rowRenderCalls === 0, "Layer thumbnails rendered scene objects");
    console.log("workspace-layers: catalog, geometry and virtualization checks passed");
    await first.focus();
    const zoom = await page.evaluate(() => canvas.getZoom());
    await first.press("Enter");
    check(await first.getAttribute("aria-selected") === "true", "Enter did not select the focused row");
    const reveal = await page.evaluate(() => {
      const point = fabric.util.transformPoint(canvas.getActiveObject().getCenterPoint(), canvas.viewportTransform);
      return Math.hypot(point.x - canvas.width / 2, point.y - canvas.height / 2);
    });
    check(reveal < 1 && await page.evaluate(() => canvas.getZoom()) === zoom, "Enter reveal changed zoom or missed the object");
    await rows.nth(1).focus();
    await rows.nth(1).press("Shift+Space");
    check(await page.evaluate(() => selectedVinylObjects().length) === 2, "Keyboard range selection failed");
    await first.focus();
    await first.press("Control+Space");
    check(await page.evaluate(() => selectedVinylObjects().length) === 1, "Keyboard toggle selection failed");
    check(await first.getAttribute("aria-selected") === "false", "Selection state did not synchronize");
    check(await snapshot() === original && await page.evaluate(() => editorHistory.entries.length) === initialHistory,
      "Selection or reveal changed artwork/history");
    console.log("workspace-layers: keyboard selection and reveal passed");

    await first.focus();
    await first.press("Space");
    const beforeNudge = await snapshot();
    await first.press("ArrowRight");
    await page.evaluate(() => flushPendingNudgeHistory());
    check(await snapshot() !== beforeNudge, "Row keyboard handler intercepted the existing arrow nudge");
    await page.locator("#undoBtn").click();
    await page.waitForFunction(() => !editorCommands.busy);
    check(await snapshot() === original, "Arrow nudge undo changed unrelated artwork");

    for (const [selector, field] of [[".layerVisibility", "visible"], [".layerLock", "locked"]]) {
      const before = await snapshot();
      const initialPressed = await first.locator(selector).getAttribute("aria-pressed");
      await first.locator(selector).focus();
      await first.locator(selector).press("Enter");
      const state = await page.evaluate(({ selector, field }) => {
        const row = document.querySelector("#layers .layerRow"), button = row.querySelector(selector);
        const object = layerListRows.get(row.dataset.layerListKey).object;
        return { pressed: button.getAttribute("aria-pressed"), value: field === "visible" ? object.visible !== false : Boolean(object.kloudy.locked),
          focused: document.activeElement === button, label: button.getAttribute("aria-label"), title: button.dataset.workspaceTooltip };
      }, { selector, field });
      check(state.pressed !== initialPressed && state.pressed === String(state.value), `${field} control disagrees with artwork`);
      check(state.focused && state.label === state.title, `${field} control lost keyboard focus or its label`);
      await page.locator("#undoBtn").click();
      await page.waitForFunction(() => !editorCommands.busy);
      check(await snapshot() === before, `${field} undo did not restore exact artwork`);
      check(await first.locator(selector).getAttribute("aria-pressed") === initialPressed, `${field} undo left stale row state`);
    }

    const reorderBefore = await snapshot();
    const source = await rows.nth(1).locator(".layerMain").boundingBox();
    const target = await first.locator(".layerMain").boundingBox();
    await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2);
    await page.mouse.down();
    await page.mouse.move(target.x + target.width / 2, target.y + 1, { steps: 15 });
    await page.mouse.up();
    check(await snapshot() !== reorderBefore, "Layer drag did not reorder");
    const reordered = JSON.parse(await snapshot()), previous = new Map(JSON.parse(reorderBefore).map(shape => [shape.editor_id, JSON.stringify(shape)]));
    check(reordered.every(shape => previous.get(shape.editor_id) === JSON.stringify(shape)), "Reorder changed layer content");
    await page.locator("#undoBtn").click();
    await page.waitForFunction(() => !editorCommands.busy);
    check(await snapshot() === original, "Reorder undo did not restore exact stack");
    console.log("workspace-layers: nudge, visibility, lock and reorder undo passed");

    await page.locator("#layerSearch").fill('Group <test> & "name"');
    await page.waitForFunction(() => layerListEntries.length === 4);
    const group = page.locator("#layers .layerGroupRow");
    check(await group.getAttribute("aria-expanded") === "true", "Group expansion state missing");
    check(await group.locator(".layerGroupVisibility").getAttribute("aria-pressed") === "mixed", "Mixed group visibility missing");
    check(await group.locator(".layerGroupLock").getAttribute("aria-pressed") === "mixed", "Mixed group locks missing");
    await rows.first().focus();
    await rows.first().press("Space");
    check(await group.getAttribute("aria-selected") === "true", "Group selection did not follow its selected child");
    check(await rows.first().getAttribute("aria-selected") === "true", "Filtered row selection missing");
    check(await snapshot() === original, "Filtering changed artwork");
    for (const selector of [".layerGroupVisibility", ".layerGroupLock"]) {
      await group.locator(selector).focus();
      await group.locator(selector).press("Enter");
      check(await group.locator(selector).getAttribute("aria-pressed") !== "mixed", "Group control did not synchronize");
      await page.locator("#undoBtn").click();
      await page.waitForFunction(() => !editorCommands.busy);
      check(await snapshot() === original, "Group control undo changed artwork");
      check(await group.locator(selector).getAttribute("aria-pressed") === "mixed", "Group undo lost mixed state");
    }
    await page.locator("#layerSearch").fill("no matching workspace layer");
    check(await rows.count() === 0, "Empty filtering retained rows");
    await page.locator("#layerSearch").fill("");
    await page.evaluate(() => { const pane = layerScrollPane(); pane.scrollTop = pane.scrollHeight; renderVirtualLayerWindow(true); });
    check(await rows.count() < 45 && await group.count() === 1, "Virtual scrolling failed to reach the final group");
    await group.locator(".layerGroupTwist").focus();
    await group.locator(".layerGroupTwist").press("Enter");
    fs.writeFileSync(path.join(output, "group-focus.json"), JSON.stringify(await page.evaluate(() => ({
      collapsed: [...collapsedLayerGroups], focus: document.activeElement.outerHTML.slice(0, 1000),
      row: document.querySelector(".layerGroupRow")?.outerHTML.slice(0, 2000), scroll: layerScrollPane().scrollTop,
    })), null, 2));
    check(await group.getAttribute("aria-expanded") === "false", "Group collapse state did not synchronize");
    await group.locator(".layerGroupTwist").press("Enter");
    check(await group.getAttribute("aria-expanded") === "true", "Group expand lost keyboard focus");
    check(await snapshot() === original, "Group collapse/expand changed artwork");
    console.log("workspace-layers: filtering, mixed group state and keyboard collapse passed");

    await page.locator("#layerSearch").fill("Layer 2999");
    await page.waitForFunction(() => layerListEntries.length === 1);
    await page.route("**/Resources/Vinyls/Primitives/3.png", route => route.fulfill({ contentType: "image/png", body: "invalid PNG" }));
    await page.evaluate(() => renderVirtualLayerWindow(true));
    await page.waitForFunction(() => document.querySelector(".layerThumbnail")?.dataset.preview === "geometry");
    check(await first.locator(".layerThumbnail svg polygon").count() === 1, "Missing catalog PNG did not use safe native geometry");
    await page.unroute("**/Resources/Vinyls/Primitives/3.png");
    await page.evaluate(() => renderVirtualLayerWindow(true));
    await page.waitForFunction(() => { const image = document.querySelector(".layerThumbnail img"); return image?.complete && image.naturalWidth > 0; });
    check(await snapshot() === original, "Thumbnail fallback changed artwork");
    await page.locator("#layerSearch").fill("");
    await first.focus();
    await first.press("Space");
  }
  await page.screenshot({ path: path.join(output, `workspace-layers-${layerCount}.png`) });
  const nativeSaveAs = async (name) => {
    const menu = await page.locator("#saveProjectAs").evaluate(button => button.closest(".workspaceMenu")?.id || "");
    if (menu) await page.locator(`[aria-controls="${menu}"]`).click();
    await page.locator("#saveProjectAs").click();
    await page.locator("#textPromptInput").fill(name);
    await page.locator("#textPromptInput").press("Enter");
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  };
  await nativeSaveAs("Workspace layer presentation");
  const exactArtwork = await snapshot() === original;
  check(exactArtwork, "Native Save As changed layer content");
  const assert = require("node:assert/strict");
  // Compare the JSON contract, including its standard normalization of negative zero.
  const expectedPortable = await page.evaluate(() => JSON.parse(JSON.stringify(
    vinylObjects().map(object => objectToShape(object, { includeEditorMeta: false })))));
  const nativeProcess = JSON.parse(fs.readFileSync(path.join(output, "process.json"), "utf8"));
  const projects = path.join(nativeProcess.profile, "projects");
  const projectFiles = fs.readdirSync(projects).filter(name => name.endsWith(".fabric-project.json"));
  check(projectFiles.length === 1, "Save As did not create exactly one native project");
  const savedProject = JSON.parse(fs.readFileSync(path.join(projects, projectFiles[0]), "utf8"));
  check(savedProject.format === "kloudy_fabric_editor_project_v1", "Native project format changed");
  assert.deepStrictEqual(savedProject.shapes, JSON.parse(original), "Native project lost layer metadata or artwork");
  check(await page.locator("#exportJson").isVisible(), "Header Export JSON is not visible");
  check(await page.locator("#exportJson").evaluate(button => Boolean(button.closest("header, .appBar"))),
    "Export JSON is no longer a header action");
  await page.locator("#exportJson").click();
  await page.waitForFunction(() => !exportSaveInProgress && !jsonBrowserState.loading && selectedJsonBrowserEntry()?.id);
  const exported = await page.evaluate(async () => {
    const entry = selectedJsonBrowserEntry();
    if (jsonBrowserState.source !== "editor") throw new Error("Export did not select Editor exports");
    const data = await readEditorDocument(`${JSON_FILE_API}?id=${encodeURIComponent(entry.id)}`);
    return { entry, data };
  });
  check(exported.data.name === exported.entry.name, "JSON browser read back a different file");
  const exportRoot = path.resolve(nativeProcess.exportRoot);
  const exportFile = path.resolve(nativeProcess.appRoot, exported.data.id);
  const exportRelative = path.relative(exportRoot, exportFile);
  check(exportRelative && exportRelative !== ".." && !exportRelative.startsWith(`..${path.sep}`)
    && !path.isAbsolute(exportRelative), "Exported file escaped its isolated test directory");
  const diskExport = JSON.parse(fs.readFileSync(exportFile, "utf8"));
  assert.deepStrictEqual(diskExport, exported.data.payload, "Backend JSON read did not match the saved disk file");
  assert.deepStrictEqual(diskExport.shapes, expectedPortable, "Header export changed layer count, order, names or geometry");
  check(Object.keys(diskExport).length === 1 && Array.isArray(diskExport.shapes), "Export leaked project-level metadata");
  const editorKeys = diskExport.shapes.flatMap(shape => Object.keys(shape).filter(key => key.startsWith("editor_")));
  check(editorKeys.length === 0, "Export leaked editor-only layer metadata");
  const beforeReopen = await page.evaluate(() => documentIdentity);
  await fixture.fileInput(page, "#jsonInput", exportFile);
  await page.waitForFunction(({ previous, count }) => documentIdentity > previous && vinylObjects().length === count
    && document.getElementById("busyBanner").hidden && !recoveryRestoreDepth,
  { previous: beforeReopen, count: layerCount });
  const reopened = await page.evaluate(() => ({
    shapes: JSON.parse(JSON.stringify(vinylObjects().map(object => objectToShape(object, { includeEditorMeta: false })))),
    cleanEditorState: vinylObjects().every(object => object.visible !== false && !object.kloudy.locked
      && !object.kloudy.group_id),
    source: loadedName,
  }));
  assert.deepStrictEqual(reopened.shapes, expectedPortable, "Actual file-input reopen changed exported layer content");
  check(reopened.cleanEditorState, "Portable import retained hidden, locked or grouped project-only state");
  await nativeSaveAs("Workspace layer portable reopen");
  assert.deepStrictEqual(JSON.parse(fs.readFileSync(path.join(projects, projectFiles[0]), "utf8")), savedProject,
    "Export/reopen modified the original native project");
  const exportRoundtrip = { layers: reopened.shapes.length, nativeProject: projectFiles[0], exportedFile: exportFile,
    backendDiskExact: true, portableContentExact: true, editorKeys, cleanEditorState: reopened.cleanEditorState,
    originalProjectUnchanged: true, importPath: "actual #jsonInput via CDP file selection" };
  fs.writeFileSync(path.join(output, "export-roundtrip.json"), JSON.stringify(exportRoundtrip, null, 2));
  console.log("workspace-layers: native Save As, header export, backend/disk read and actual file-input reopen passed");
  await page.evaluate(async () => { await flushPendingAutosave(); await KfpsEditorPreferences.flush(); });
  return { passed: true, mode: exportOnly ? "export-only" : "full", layerCount, presentation, rowRenderCalls, exactArtwork, exportRoundtrip,
    checks: [...(exportOnly ? [] : ["3000-layer import", "catalog thumbnails", "62px stride", "bounded virtual rows", "escaped names",
      "keyboard selection/reveal", "arrow nudge preserved", "visibility/lock and undo", "pointer reorder and undo",
      "filtering", "mixed group state", "group controls/collapse/focus", "PNG failure geometry fallback"]), "native save",
      "header Export JSON", "real backend/disk readback", "clean export metadata", "actual file-input roundtrip"],
    qualification: "Offscreen native Qt workflow; not foreground GPU or assistive-technology qualification." };
}
