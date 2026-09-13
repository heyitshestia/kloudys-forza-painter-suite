async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  page.setDefaultTimeout(30000);
  const initial = await h.setup(page, output, options);
  const original = await h.snapshot(page);
  const key = options.target || "Primitives/27";
  const id = await page.evaluate(key => vinylObjects().filter(o => `${o.kloudy.resource_family}/${o.kloudy.resource_index}` === key)
    .sort((a, b) => b.getScaledWidth() * b.getScaledHeight() - a.getScaledWidth() * a.getScaledHeight())[0]?.kloudy.editor_id, key);
  h.check(id, "No actual handmade handle target for " + key);
  await h.selectId(page, id);
  await page.locator("#bringFront").click();
  const exposed = await h.snapshot(page);
  const handles = ["tl", "tr", "bl", "br", "ml", "mr", "mt", "mb"];
  const combinations = Array.from({ length: 8 }, (_, mask) => ["Shift", "Control", "Alt"].filter((_, index) => mask & (1 << index)));
  const trace = await h.monitor(page, output), cases = [];
  try {
    for (const guide of options.guides || ["none", "horizontal", "vertical", "angled"]) {
      await h.selectId(page, id);
      await h.frameSelection(page);
      await page.locator('[data-tool-mode="guides"]').click();
      await page.locator("#clearGuides").click();
      await page.locator("#gridEnabled").uncheck();
      await page.locator("#snapCtrlOnly").check();
      await page.locator("#snapGuideAnchor").uncheck();
      await page.locator("#snapGuideEnd").uncheck();
      await page.locator("#guideConstraint").selectOption(guide === "horizontal" || guide === "vertical" ? guide : "free");
      if (guide !== "none") {
        const box = await page.locator(".upper-canvas").boundingBox();
        const from = { x: box.x + box.width * (guide === "vertical" ? .5 : .25), y: box.y + box.height * (guide === "horizontal" ? .5 : .25) };
        const to = { x: box.x + box.width * (guide === "vertical" ? .5 : .75), y: box.y + box.height * (guide === "horizontal" ? .5 : .75) };
        await h.motion(page, from, to, "ordinary");
        h.check(await page.evaluate(() => guideState.guides.length) === 1, "Real guide drawing did not create one line");
      }
      await page.locator('[data-tool-mode="select"]').click();
      await h.selectId(page, id);
      for (const speed of options.speeds || Object.keys(h.speeds)) for (const modifiers of combinations) for (const handle of handles) {
        const label = `${key}/${guide}/${speed}/${modifiers.join("+") || "plain"}/${handle}`;
        const before = await h.snapshot(page);
        const geometry = await h.geometry(page), point = geometry.handles[handle];
        fs.writeFileSync(path.join(output, "handle-phase.json"), JSON.stringify({ label, completed: cases.length }));
        let timing, after;
        await trace.run(label, async () => {
          timing = await h.motion(page, point, { x: point.x + (handle.includes("l") ? -17 : 17),
            y: point.y + (handle.includes("t") ? -13 : 13) }, speed, modifiers);
          after = await h.geometry(page);
          h.check(JSON.stringify(after.shape.data) !== JSON.stringify(geometry.shape.data), "Handle did not change shape");
          h.check(after.shape.data.every(Number.isFinite) && Math.abs(after.shape.data[2]) > 1e-6 && Math.abs(after.shape.data[3]) > 1e-6,
            "Handle produced invalid/zero geometry");
          if (modifiers.includes("Shift") && ["tl", "tr", "bl", "br"].includes(handle))
            h.check(Math.abs(after.skewX - geometry.skewX) + Math.abs(after.skewY - geometry.skewY) > .001, "Shift corner did not skew");
        });
        const actual = JSON.parse(await h.snapshot(page)), previous = JSON.parse(before);
        h.check(actual.every((shape, index) => shape.editor_id === id || JSON.stringify(shape) === JSON.stringify(previous[index])), "Handle changed unrelated handmade artwork");
        await h.undo(page, before);
        cases.push({ label, timing, data: after.shape.data, exactUndo: true, unrelatedPreserved: true });
        fs.writeFileSync(path.join(output, "handmade-handle-cases.json"), JSON.stringify(cases, null, 2));
      }
    }
    h.check(await h.snapshot(page) === exposed, "Handle matrix altered the exposed baseline");
    for (let i = 0; i < 30 && await h.snapshot(page) !== original; i++) {
      await page.locator("#undoBtn").click();
      await page.waitForFunction(() => !editorCommands.busy);
    }
    h.check(await h.snapshot(page) === original, "Handle matrix did not restore the original layer order");
    await h.saveAs(page, "Handmade handle checkpoint");
    await page.evaluate(async () => { await flushPendingAutosave(); });
    return { initial, key, id, cases, rows: trace.rows, realGuideDrawing: true, realHandles: true,
      exactArtwork: true, limitations: "Guides present during transforms; exact guide-contact qualification is separate" };
  } finally { await trace.close(); }
}
