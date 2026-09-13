async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  page.setDefaultTimeout(30000);
  const initial = options.derived ? await h.setupDerived(page, output, { ...options, layers: 2950 }) : await h.setup(page, output, options);
  const originalCount = initial.layers, start = Date.now(), minutes = Number(options.minutes || 25);
  h.check(Number.isFinite(minutes) && minutes >= 1 && minutes <= 30, "Endurance duration must be between one and thirty minutes");
  const ids = await page.evaluate(() => [
    ["Primitives", 27], ["Primitives", 30], ["Primitives", 36], ["Primitives", 2],
    ["Community_Vinyls_1", 3], ["Gradient_Shapes", 13],
  ].map(([family, index]) => vinylObjects().filter(o => o.kloudy.resource_family === family && o.kloudy.resource_index === index)
    .sort((a, b) => b.getScaledWidth() * b.getScaledHeight() - a.getScaledWidth() * a.getScaledHeight())[0]?.kloudy.editor_id).filter(Boolean));
  h.check(ids.length===6,"Endurance is missing a required resource family");
  const trace = await h.monitor(page, output), checkpoints = [], motions = [];
  let cycle = 0;
  const compact = () => page.evaluate(() => ({ layers: vinylObjects().length, history: editorHistory.entries.length,
    historyIndex: editorHistory.index, recovery: editorRecovery.status, pendingWorkerRequests: editorPersistence.pending.size,
    acceptedCommit: contentCommitId, durableCommit: durableCommitId,
    zoom: canvas.getZoom(), preview: editorRenderer.active, fallback: editorRenderer.disabledReason,
    hidden: document.hidden, reference: [editorReference.image?.width, editorReference.image?.height],
    cachePixels: vinylObjects().reduce((sum, object) => sum + (object._cacheCanvas?.width || 0) * (object._cacheCanvas?.height || 0), 0) }));
  try {
    while (Date.now() - start < minutes * 60000) {
      const batchStart = Date.now();
      await trace.run(`minute-${checkpoints.length + 1}`, async () => {
        do {
          h.check(!fs.existsSync(path.join(output, "stop-test.json")), "External memory guard requested a safe stop");
          const id = ids[cycle % ids.length], speed = Object.keys(h.speeds)[Math.floor(cycle / ids.length) % 4];
          const order=Math.floor(cycle / (ids.length * 4)) % 2 ? "below" : "above";
          if (cycle % 6 === 0) {
            await page.locator('[data-tool-mode="overlay"]').click();
            await page.locator("#overlayLayerMode").selectOption(order);
            await page.locator('[data-tool-mode="select"]').click();
          }
          await h.selectId(page, id);
          await page.locator("#bringFront").click();
          await h.frameSelection(page);
          const geometry = await h.geometry(page), r = geometry.handles.mtr, c = geometry.center;
          const angle = Math.floor(cycle / ids.length) % 2 ? -.17 : .17;
          const dx = r.x - c.x, dy = r.y - c.y;
          const timings = [];
          timings.push(await h.motion(page, r, { x: c.x + dx * Math.cos(angle) - dy * Math.sin(angle),
            y: c.y + dx * Math.sin(angle) + dy * Math.cos(angle) }, speed));
          const rotated = await h.geometry(page);
          h.check(Math.abs(rotated.angle - geometry.angle) > 2, "Endurance rotation was not applied");
          timings.push(await h.motion(page, rotated.grab, { x: rotated.grab.x + 13, y: rotated.grab.y + 8 }, speed));
          const moved = await h.geometry(page);
          await h.expectTranslation(page,rotated,moved,13,8);
          h.check(Math.hypot(moved.left - rotated.left, moved.top - rotated.top) > .01, "Endurance immediate drag did not apply");
          await page.mouse.move(moved.center.x, moved.center.y);
          for (const delta of [-100, 100, -100, 100]) await page.mouse.wheel(0, delta);
          const zoomed = await h.geometry(page);
          timings.push(await h.motion(page, zoomed.grab, { x: zoomed.grab.x - 13, y: zoomed.grab.y - 8 }, speed));
          const after = await h.geometry(page);
          await h.expectTranslation(page,zoomed,after,-13,-8);
          h.check(after.shape.data.every(Number.isFinite) && Math.hypot(after.left - zoomed.left, after.top - zoomed.top) > .01,
            "Endurance move after zoom failed or invalidated geometry");
          if (cycle % 5 === 0) {
            const box = await page.locator(".upper-canvas").boundingBox();
            const p = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
            timings.push(await h.motion(page, p, { x: p.x + 22, y: p.y + 14 }, speed, [], cycle % 10 ? "right" : "middle"));
          }
          if (cycle % 9 === 0) {
            await page.locator("#undoBtn").click(); await page.waitForFunction(() => !editorCommands.busy);
            await page.locator("#redoBtn").click(); await page.waitForFunction(() => !editorCommands.busy);
          }
          motions.push({ cycle, id, speed, order, elapsedMs: Date.now() - start, timings });
          cycle++;
        } while (Date.now() - batchStart < 60000 && Date.now() - start < minutes * 60000);
      });
      const state = await compact();
      h.check(state.layers === originalCount && !state.hidden && state.reference[0] === initial.reference[0], "Endurance lost artwork, reference or foreground rendering eligibility");
      h.check(state.history<=80,"Endurance history exceeded its retention limit");
      h.check(state.durableCommit>(checkpoints.at(-1)?.durableCommit||0),"Background recovery did not advance during the latest editing minute");
      const combinations=new Set(motions.map(item=>`${item.id}/${item.speed}/${item.order}`)).size;
      if(cycle>=48)h.check(combinations===48,"Sustained input did not cross every resource, speed and reference order");
      checkpoints.push({ minute: checkpoints.length + 1, elapsedMs: Date.now() - start, cycle, combinations, ...state });
      fs.writeFileSync(path.join(output, "endurance-checkpoints.json"), JSON.stringify(checkpoints, null, 2));
      fs.writeFileSync(path.join(output, "endurance-motions.json"), JSON.stringify(motions, null, 2));
    }
    const idleStart = Date.now();
    await page.waitForFunction(() => editorRecovery.status.serverOk && editorRecovery.status.browserOk, null, { timeout: 20000 });
    const naturalRecoveryMs = Date.now() - idleStart;
    const expected = await h.snapshot(page);
    await h.saveAs(page, "Handmade endurance checkpoint");
    await page.evaluate(async () => { await flushPendingAutosave(); });
    const exactRecovery = await page.evaluate(async () => JSON.stringify((await readAutosavePayload()).shapes) === JSON.stringify(snapshotShapes()));
    h.check(exactRecovery, "Final endurance recovery differs from artwork");
    fs.writeFileSync(path.join(output, "endurance-expected.json"), expected);
    fs.writeFileSync(path.join(output, "endurance-reference.json"), JSON.stringify(await h.referenceState(page)));
    await page.locator("#fitView").click();
    await page.screenshot({ path: path.join(output, "endurance-final.png") });
    return { initial, minutes, cycle, checkpoints, rows: trace.rows, naturalRecoveryMs, exactRecovery,
      noForcedGC: true, noRepeatedFullRecoveryReadback: true, inputPath: "Actual project browser, layer rows, controls, pointer and keyboard" };
  } finally { await trace.close(); }
}
