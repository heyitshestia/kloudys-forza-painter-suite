async (page, options = {}) => {
  const h = require(path.join(__dirname, "dense-human-fixture.cjs"));
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const idle = () => page.waitForFunction(() => !editorCommands.busy && !projectAdditionPending && !projectSaveInProgress && !editorAssetLibrary.busy);
  const snapshot = () => h.snapshot(page);
  const prompt = async name => {
    await page.locator("#textPromptInput").fill(name);
    await page.locator("#textPromptInput").press("Enter");
    await idle();
  };
  const saveAs = async name => { await page.locator("#saveProjectAs").click(); await prompt(name); };
  const choose = async name => {
    await page.locator("#loadProject").click();
    await page.locator(".projectBrowserEntry").filter({ hasText: name }).first().click();
  };
  const add = async name => { await choose(name); await page.locator("#addProjectEntry").click(); await idle(); };
  const checks = [];
  if (options.restart) {
    const expected = JSON.parse(fs.readFileSync(options.expected, "utf8"));
    await page.waitForFunction(count => vinylObjects().length === count && !recoveryRestoreDepth, expected.shapes.length);
    const actual = await page.evaluate(() => editableProjectPayload(currentProjectName));
    check(JSON.stringify(actual) === JSON.stringify(expected), "Native restart changed the combined project");
    check(await page.evaluate(() => documentDirty), "Unsaved combined project incorrectly recovered as saved");
    await page.locator("#saveProject").click(); await idle();
    check(await page.evaluate(() => !documentDirty && Boolean(editorProjects.association)), "Recovered project did not save to its destination");
    return { passed: true, checks: ["native crash/restart restores exact 3,000-shape hierarchy and unsaved destination association"] };
  }

  await page.evaluate(async () => {
    const shapes = Array.from({ length: 120 }, (_, i) => ({
      type: [1048677, 1048678, 1048706][i % 3],
      data: [-260 + i % 20 * 26, 160 - Math.floor(i / 20) * 36, i % 7 ? .2 : -.2, .3, i * 7 % 360, i % 5 * .04, i === 3 ? 1 : 0],
      color: [100 + i % 100, 190, 100, i % 3 ? 230 : 120], mask: i === 3,
      shape_name: `Inserted layer ${i}`, editor_id: `source-${i}`,
      editor_locked: i === 1, editor_hidden: i === 2,
      ...(i < 80 ? { editor_group_id: i < 40 ? "child-a" : "child-b", editor_group_name: i < 40 ? "Child A" : "Child B",
        editor_group_path: [{ id: "source-root", name: "Original parent" }, { id: i < 40 ? "child-a" : "child-b", name: i < 40 ? "Child A" : "Child B" }] } : {}),
    }));
    await loadProjectPayload({ format: "kloudy_fabric_editor_project_v1", name: "Source piece", shapes,
      editor_collapsed_groups: ["child-a"] }, "Source piece");
    window.addSourceShapes = snapshotShapes();
  });
  await saveAs("Source piece");
  const sourceReceipt = await page.evaluate(() => editorProjects.association);
  const processInfo = JSON.parse(fs.readFileSync(path.join(output, "process.json"), "utf8"));
  const sourcePath = path.resolve(processInfo.profile, "projects", sourceReceipt.target_id);
  check(sourcePath.startsWith(path.resolve(processInfo.profile, "projects") + path.sep), "Source fixture escaped isolated profile");
  const sourceBytes = fs.readFileSync(sourcePath);
  await h.setup(page, output, { layers: 2400 });
  await page.evaluate(async () => {
    const image = document.createElement("canvas"); image.width = 64; image.height = 64;
    const ctx = image.getContext("2d"); ctx.fillStyle = "#3caabb"; ctx.fillRect(0, 0, 64, 64);
    await editorReference.restoreSourceOverlayFromProject({ version: 1, file_name: "Destination reference",
      data_url: image.toDataURL(), transform: { left: 100, top: 200, scaleX: 8, scaleY: 8, opacity: .3 },
      controls: { scale_percent: 100, opacity_percent: 30, layer_mode: "bottom" } });
    applySavedGuideState({ version: 1, gridSize: 37, guides: [{ id: "dest-guide", x1: -250, y1: -200, x2: 250, y2: 200, constraint: "free" }] });
    pushHistory("destination setup");
  });
  await saveAs("Destination canvas");
  const before = await snapshot();
  const environment = await page.evaluate(() => ({ name: currentProjectName, reference: editorReference.sourceOverlayProjectState(), guides: savedGuideState(),
    viewport: [...canvas.viewportTransform], receipt: editorProjects.association, identity: documentIdentity, history: editorHistory.index }));
  const monitor = await h.monitor(page, output);
  try {
    await monitor.run("add-120-to-2400", () => add("Source piece"));
    check(await page.locator("#projectBrowserDialog").isHidden(), "Successful Add did not close the project browser");
    const added = await page.evaluate(env => {
      const shapes = snapshotShapes(), incoming = shapes.slice(2400);
      const canonical = shape => {
        const copy = { ...shape }; for (const key of Object.keys(copy)) if (key.startsWith("editor_")) delete copy[key];
        return copy;
      };
      for (let i = 0; i < incoming.length; i++) {
        const a = canonical(incoming[i]), b = canonical(addSourceShapes[i]);
        if (JSON.stringify(a) !== JSON.stringify(b)) throw Error(`Incoming geometry/color/mask changed at ${i}: ${JSON.stringify({ a, b })}`);
        if (incoming[i].editor_id === addSourceShapes[i].editor_id) throw Error("Source shape identity reused");
        if (incoming[i].editor_locked !== addSourceShapes[i].editor_locked || incoming[i].editor_hidden !== addSourceShapes[i].editor_hidden) throw Error("Incoming lock/visibility changed");
      }
      if (JSON.stringify(editorReference.sourceOverlayProjectState()) !== JSON.stringify(env.reference)
        || JSON.stringify(savedGuideState()) !== JSON.stringify(env.guides)
        || JSON.stringify(canvas.viewportTransform) !== JSON.stringify(env.viewport)
        || JSON.stringify(editorProjects.association) !== JSON.stringify(env.receipt)
        || currentProjectName !== env.name || documentIdentity !== env.identity) throw Error("Add replaced destination state");
      if (editorHistory.index !== env.history + 1) throw Error("Add is not one undo step");
      return { before: JSON.stringify(shapes.slice(0, 2400)), count: shapes.length, outer: KfpsEditorLayerGroups.shapePath(incoming[0])[0].id,
        depths: [KfpsEditorLayerGroups.shapePath(incoming[0]).length, KfpsEditorLayerGroups.shapePath(incoming[119]).length] };
    }, environment);
    check(added.count === 2520 && added.before === before && added.depths.join() === "3,1", "Added scene/hierarchy differs");
    check(fs.readFileSync(sourcePath).equals(sourceBytes), "Add wrote to source project");
    const after = await snapshot();
    await h.undo(page, before); await page.locator("#redoBtn").click(); await idle();
    check(await snapshot() === after, "Redo changed independent copies");
    checks.push("2,400 + 120: geometry, skew, rotation, mirror, mask, alpha, hidden/locked, nested paths; source unchanged; one-step exact undo/redo; destination reference/guides/viewport/save target unchanged");

    await h.select(page, "Source piece", true);
    await page.locator("#renameSelectedGroup").click(); await prompt("Independent copy");
    check(await page.evaluate(id => membersForGroupIds([id]).every(o => KfpsEditorLayerGroups.objectPath(o)[0].name === "Independent copy"), added.outer), "Outer rename failed");
    await page.locator("#ungroupSelected").click(); await idle();
    check(await page.evaluate(() => KfpsEditorLayerGroups.objectPath(vinylObjects()[2400]).map(g => g.name).join() === "Original parent,Child A"), "Ungroup removed nested groups");
    await page.locator("#undoBtn").click(); await idle(); await page.locator("#undoBtn").click(); await idle();
    check(await snapshot() === after, "Nested actions undo differs");
    await page.locator("#layerSearch").fill("");
    await monitor.run("repeat-add-independent-copy", () => add("Source piece"));
    check(await page.evaluate(() => {
      const s = snapshotShapes();
      return s.length === 2640 && new Set(s.map(v => v.editor_id)).size === s.length
        && KfpsEditorLayerGroups.shapePath(s[2400])[0].id !== KfpsEditorLayerGroups.shapePath(s[2520])[0].id;
    }), "Repeated Add collided with previous copy");
    const twice = await snapshot();
    checks.push("outer-group rename/ungroup preserve children; repeated Add has unique identities");

    for (const [button, field] of [["#hideSelectedGroup", "visibility"], ["#lockSelectedGroup", "lock"]]) {
      await h.select(page, "Source piece", true);
      await page.locator(button).click(); await idle();
      check(await page.evaluate(field => {
        const members = selectedGroupMembers();
        return members.length === 120 && members.every(o => field === "visibility" ? !o.visible : o.kloudy.locked);
      }, field), `Outer ${field} missed nested members`);
      await h.undo(page, twice);
    }
    await h.select(page, "Child B", true);
    const selectionLayout = await page.evaluate(() => {
      const info = document.getElementById("layerInfo"), search = document.getElementById("layerSearch");
      return { client: info.clientHeight, content: info.scrollHeight, bottom: info.getBoundingClientRect().bottom, next: search.getBoundingClientRect().top };
    });
    check(selectionLayout.client >= selectionLayout.content && selectionLayout.bottom <= selectionLayout.next, `Selection text overlaps search: ${JSON.stringify(selectionLayout)}`);
    await page.screenshot({ path: path.join(output, "nested-groups.png") });
    await monitor.run("drag-imported-nested-child-40-shapes", async () => {
      const p = await h.geometry(page);
      await h.drag(page, p.grab, { x: p.grab.x + 28, y: p.grab.y - 17 }); await idle();
    });
    const childMove = await page.evaluate(() => snapshotShapes());
    const oldTwice = JSON.parse(twice);
    const changed = childMove.map((s, i) => JSON.stringify(s) === JSON.stringify(oldTwice[i]) ? -1 : i).filter(i => i >= 0);
    check(changed.length === 40 && changed.every(i => i >= 2560 && i < 2600), `Child drag affected unrelated layers: ${changed}`);
    await h.undo(page, twice);
    checks.push("outer hide/lock affect all nested members; real child-group drag moves only its 40 shapes; exact undo");
    await page.evaluate(() => selectObjects(vinylObjects().slice(2520), "nested selection"));

    await page.locator('[data-panel="assetsPane"]').click();
    await page.locator("#assetSaveSelection").click(); await prompt("Independent nested asset");
    await page.locator(".editorAsset").filter({ hasText: "Independent nested asset" }).locator(".assetActions > button").first().click(); await idle();
    check(await page.evaluate(() => vinylObjects().length === 2760 && KfpsEditorLayerGroups.objectPath(vinylObjects()[2640]).length === 3), "Asset lost nested groups");
    await h.undo(page, twice);
    await page.evaluate(() => selectObjects(vinylObjects().slice(2520), "nested selection"));
    await page.locator("#copyLayer").click(); await page.locator("#pasteLayer").click(); await idle();
    check(await page.evaluate(() => vinylObjects().length === 2760 && KfpsEditorLayerGroups.objectPath(vinylObjects()[2640]).length === 3), "Clipboard lost nested groups");
    await h.undo(page, twice);
    await page.evaluate(() => selectObjects(vinylObjects().slice(2520), "nested selection"));
    await page.locator("#duplicateLayer").click(); await idle();
    check(await page.evaluate(() => vinylObjects().length === 2759
      && vinylObjects().slice(2640).some(o => KfpsEditorLayerGroups.objectPath(o).at(-1)?.name === "Child B")
      && vinylObjects().slice(2640).every(o => !o.kloudy.locked)), "Duplicate lost complete nested child or copied locked layer");
    await h.undo(page, twice);
    checks.push("nested Assets save/insert, clipboard and unlocked duplication; exact undo");

    await page.locator("#saveProject").click(); await idle();
    const saved = await page.evaluate(() => editableProjectPayload(currentProjectName));
    fs.unlinkSync(sourcePath);
    await page.evaluate(async () => {
      const disk = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(editorProjects.association.target_id)}`);
      await loadProjectPayload(disk.payload, disk.payload.name, { receipt: disk.receipt });
    });
    await page.waitForFunction(() => editorReference.image && !recoveryRestoreDepth);
    check(JSON.stringify(await page.evaluate(() => editableProjectPayload(currentProjectName))) === JSON.stringify(saved), "Deleting source changed destination on reopen");
    await page.locator("#exportJson").click();
    await page.waitForFunction(() => !exportSaveInProgress);
    const exportFiles = fs.readdirSync(processInfo.exportRoot, { recursive: true }).filter(name => name.endsWith(".fh6-import.json"));
    check(exportFiles.length === 1, "Export button did not create one game JSON");
    const exported = JSON.parse(fs.readFileSync(path.join(processInfo.exportRoot, exportFiles[0]), "utf8"));
    check(exported.shapes.length === 2640 && exported.shapes.every(s => !Object.keys(s).some(k => k.startsWith("editor_"))), "Game export leaked editor hierarchy");
    checks.push("save/reopen exact after source file deletion; game export stays flat");

    await h.select(page, "Human target");
    await page.locator('[data-panel="propertiesPane"]').click();
    const geometryBefore = await snapshot();
    await monitor.run("rotate-drag-zoom-on-2640-layer-combined-project", async () => {
      await page.locator("#rotInput").fill("37"); await page.locator("#rotInput").press("Enter");
      const p = await h.geometry(page); await h.drag(page, p.grab, { x: p.grab.x + 40, y: p.grab.y + 20 });
      for (const delta of [-180, 180, -180, 180]) await page.mouse.wheel(0, delta);
      await page.waitForTimeout(400);
    });
    check(await snapshot() !== geometryBefore, "Gesture did not change target");
    await page.locator("#undoBtn").click(); await idle(); await page.locator("#undoBtn").click(); await idle();
    check(await snapshot() === geometryBefore, "Combined project gesture undo differs");
    checks.push("real input: rotate then drag and rapid zoom with 2,640 shapes plus reference");
    await page.locator("#saveProject").click(); await idle();
    return { passed: true, checks, timings: monitor.rows };
  } finally { await monitor.close(); }
}
