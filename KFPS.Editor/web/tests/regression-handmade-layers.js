async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  page.setDefaultTimeout(30000);
  const initial = await h.setup(page, output, options), original = await h.snapshot(page);
  const ids = h.input(options).project.shapes.slice(-6, -3).map(shape => shape.editor_id);
  const trace = await h.monitor(page, output), checks = [];
  const idle = () => page.waitForFunction(() => !editorCommands.busy);
  const restore = async expected => {
    for (let i = 0; i < 18 && await h.snapshot(page) !== expected; i++) { await page.locator("#undoBtn").click(); await idle(); }
    h.check(await h.snapshot(page) === expected, "Layer workflow did not restore exact artwork");
  };
  const multiple = async () => {
    for (let i = 0; i < ids.length; i++) await h.selectId(page, ids[i], i ? ["Control"] : []);
    h.check(await page.evaluate(() => selectedVinylObjects().length) === ids.length, "Control row multi-selection failed");
  };
  try {
    for (const button of ["bringForward", "sendBackward", "bringFront", "sendBack"]) await trace.run(`original/${button}`, async () => {
      await h.selectId(page, ids[0]);
      const before = await h.snapshot(page), shapes = JSON.parse(before), index = shapes.findIndex(shape => shape.editor_id === ids[0]);
      await page.locator(`#${button}`).click(); await idle();
      const actual = JSON.parse(await h.snapshot(page));
      const expected = button === "bringForward" ? index + 1 : button === "sendBackward" ? index - 1 : button === "bringFront" ? shapes.length - 1 : 0;
      h.check(actual.findIndex(shape => shape.editor_id === ids[0]) === expected, "Wrong layer stack destination");
      const byId = new Map(shapes.map(shape => [shape.editor_id, JSON.stringify(shape)]));
      h.check(actual.every(shape => byId.get(shape.editor_id) === JSON.stringify(shape)), "Reordering changed shape content");
      await h.undo(page, before);
    });
    for (const button of ["groupSelected", "quickGroupSelected"]) await trace.run(`original/${button}-workflow`, async () => {
      await multiple();
      const before = await h.snapshot(page);
      await page.locator(`#${button}`).click();
      const group = await page.evaluate(() => selectedGroupIds()[0]);
      h.check(group && await page.evaluate(() => selectedGroupMembers().length) === 3, "Group creation missed selected artwork");
      await page.locator("#renameSelectedGroup").click(); await h.type(page, "#textPromptInput", "Handmade group check");
      await page.locator("#textPromptInput").press("Enter");
      await page.locator("#textPromptDialog").waitFor({ state: "hidden" });
      await h.type(page, "#layerSearch", "Handmade group check");
      const row = page.locator(".layerGroupRow").filter({ hasText: "Handmade group check" });
      await row.locator(".layerGroupTwist").click();
      h.check(await page.evaluate(group => collapsedLayerGroups.has(group), group), "Group did not collapse");
      await row.locator(".layerGroupTwist").click();
      h.check(!await page.evaluate(group => collapsedLayerGroups.has(group), group), "Group did not expand");
      for (const control of [".layerGroupVisibility", ".layerGroupLock"]) {
        await row.locator(control).click(); await row.locator(control).click();
      }
      await row.click();
      await page.locator("#ungroupSelected").click();
      h.check(await page.evaluate(() => selectedVinylObjects().every(o => !o.kloudy.group_id)), "Ungroup retained group metadata");
      await restore(before);
    });
    await trace.run("original/quick-duplicate-delete-and-history", async () => {
      await h.selectId(page, ids[0]); const before = await h.snapshot(page);
      await page.locator("#quickDuplicateLayer").click();
      await page.waitForFunction(count => vinylObjects().length === count + 1, initial.layers);
      const duplicated = await h.snapshot(page);
      await page.locator("#quickDeleteLayer").click();
      await page.waitForFunction(count => vinylObjects().length === count, initial.layers);
      h.check(await h.snapshot(page) === before, "Quick Delete did not remove only the duplicate");
      await page.locator("#undoBtn").click(); await idle();
      h.check(await h.snapshot(page) === duplicated, "Quick Delete undo lost the duplicate");
      await page.locator("#redoBtn").click(); await idle();
      h.check(await h.snapshot(page) === before, "Quick Delete redo changed unrelated artwork");
    });
    await h.selectId(page,ids[0]);
    await page.locator("#clearLayerSelection").click();
    h.check(await page.evaluate(()=>selectedVinylObjects().length)===0,"Clear Selection retained a layer");
    await page.locator("#fitView").click();
    await page.locator("#overlapCycle").check();
    const point = await page.evaluate(() => {
      const rect = canvas.upperCanvasEl.getBoundingClientRect();
      for (const object of vinylObjects().slice().reverse()) {
        const center = object.getCenterPoint(), projected = fabric.util.transformPoint(center, canvas.viewportTransform);
        const q = { x: Math.round(projected.x + rect.left) - rect.left, y: Math.round(projected.y + rect.top) - rect.top };
        const inverse = fabric.util.invertTransform(canvas.viewportTransform);
        const p = fabric.util.transformPoint(q, inverse);
        if (q.x < 20 || q.y < 20 || q.x > rect.width - 20 || q.y > rect.height - 20) continue;
        const hits = overlappingVinylObjects(p);
        if (hits.length < 3) continue;
        const ids = hits.map(o => o.kloudy.editor_id), signature = JSON.stringify(ids);
        if (![[2,0],[-2,0],[0,2],[0,-2]].every(([x,y]) => JSON.stringify(overlappingVinylObjects(
          fabric.util.transformPoint({ x:q.x+x, y:q.y+y },inverse)).map(o=>o.kloudy.editor_id))===signature)) continue;
        if (hits.slice(0,3).some(hit => { hit.setCoords(); return Object.values(hit.oCoords || {}).some(c => Math.hypot(c.x-q.x,c.y-q.y)<24); })) continue;
        return { x: q.x + rect.left, y: q.y + rect.top, ids, stableRadiusPixels: 2, controlClearancePixels: 24 };
      }
      throw Error("No real three-layer overlap found");
    });
    fs.writeFileSync(path.join(output,"overlap-target.json"),JSON.stringify(point,null,2));
    await trace.run("original/click-cycle-and-overlap-menu", async () => {
      for (let index = 0; index < 3; index++) {
        await page.mouse.move(point.x,point.y);
        await page.mouse.click(point.x, point.y);
        await page.waitForTimeout(100);
        fs.appendFileSync(path.join(output,"overlap-clicks.jsonl"),JSON.stringify({index,expected:point.ids[index],
          state:await page.evaluate(()=>({selected:selectedVinylObjects().map(o=>o.kloudy.editor_id),corner:canvas.getActiveObject()?.__corner,
            pointer:canvas._absolutePointer,trace:globalThis.handmadePointerTrace?.slice(-12)}))})+"\n");
        await page.waitForFunction(id => selectedVinylObjects()[0]?.kloudy.editor_id === id, point.ids[index]);
      }
      await page.mouse.click(point.x, point.y, { button: "right" });
      const menu = page.locator('.overlapMenu[role="menu"]');
      await menu.waitFor({ state: "visible" });
      h.check(await menu.locator('button').count() === point.ids.length, "Overlap menu omitted a hittable layer");
      await page.keyboard.press("End"); await page.keyboard.press("Enter");
      await menu.waitFor({ state: "hidden" });
      h.check(await page.evaluate(() => selectedVinylObjects()[0]?.kloudy.editor_id) === point.ids.at(-1), "Keyboard overlap choice selected the wrong layer");
      await page.mouse.click(point.x, point.y, { button: "right" });
      await menu.waitFor({ state: "visible" }); await page.keyboard.press("Escape");
      await menu.waitFor({ state: "hidden" });
    });
    await page.locator("#overlapCycle").uncheck();
    h.check(await h.snapshot(page) === original, "In-place selection and layer workflows changed original artwork");
    await h.saveAs(page, "Handmade layer workflow checkpoint");
    await page.evaluate(async () => { await flushPendingAutosave(); });
    checks.push("Four depth buttons", "Control multi-selection", "Both Group buttons", "Rename/collapse/expand/group icons/ungroup",
      "Quick duplicate/delete/undo/redo", "Three in-place overlap clicks", "Overlap menu keyboard selection and Escape");
    return { initial, checks, rows: trace.rows, actualHandmadeTargets: ids, overlapLayers: point.ids.length, exactArtwork: true };
  } finally { await trace.close(); }
}
