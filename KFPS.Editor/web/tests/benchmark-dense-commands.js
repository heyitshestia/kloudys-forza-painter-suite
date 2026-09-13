async page => {
  const cdp = await page.context().newCDPSession(page);
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, index) => ({
      type: index % 10 === 0 ? 1048706 : 1048677,
      color: [40 + index % 170, 150, 210, 255],
      data: [-700 + index % 60 * 24, 600 - Math.floor(index / 60) * 24, .18, .18, 0, 0, 0],
    })) }, { projectName: null });
    const reference = document.createElement("canvas");
    reference.width = 6000; reference.height = 4000;
    const context = reference.getContext("2d");
    context.fillStyle = "#9aabad"; context.fillRect(0, 0, 6000, 4000);
    for (let index = 0; index < 100; index++) {
      context.fillStyle = `hsl(${index * 19 % 360} 45% 65%)`;
      context.fillRect(index * 57, index * 35, 300, 160);
    }
    await editorReference.loadOverlayImageFromUrl(reference.toDataURL(), "dense-command-reference.png");
    reference.width = reference.height = 1;
    fitDesignView(); await flushPendingAutosave();
  });
  await cdp.send("Profiler.enable");
  await cdp.send("Profiler.start");
  const rows = [];
  for (const count of [50, 500, 1500, 3000]) {
    const row = await page.evaluate(async count => {
      canvas.discardActiveObject();
      const selected = vinylObjects().slice(0, count);
      const start = performance.now();
      selectObjects(selected, "dense command benchmark");
      const selectMs = performance.now() - start;
      const ordering = [];
      for (let i = 0; i < 20; i++) {
        const began = performance.now();
        const ordered = orderedSelectedVinylObjects();
        ordering.push(performance.now() - began);
        if (ordered.length !== count || ordered.some((object, index) => object !== selected[index])) throw Error("Selection ordering changed artwork order");
      }
      window.commandNudges = [];
      window.commandOriginalNudge = nudgeSelected;
      nudgeSelected = (...args) => {
        const began = performance.now();
        const value = commandOriginalNudge(...args);
        commandNudges.push(performance.now() - began);
        return value;
      };
      document.activeElement?.blur();
      return { count, selectMs, ordering, before: objectToShape(selected[0]).data[0] };
    }, count);
    try {
      for (let repeat = 0; repeat < 12; repeat++) await page.keyboard.press("ArrowRight");
      Object.assign(row, await page.evaluate(async () => {
        flushPendingNudgeHistory();
        const samples = commandNudges.slice();
        const after = objectToShape(vinylObjects()[0]).data[0];
        const start = performance.now(); await undo();
        const undoMs = performance.now() - start;
        const restored = objectToShape(vinylObjects()[0]).data[0];
        return { nudges: samples, after, restored, undoMs, hidden: document.hidden, focused: document.hasFocus() };
      }));
    } finally { await page.evaluate(() => { nudgeSelected = commandOriginalNudge; }); }
    if (row.nudges.length !== 12 || Math.abs(row.after - row.before) < 1 || Math.abs(row.restored - row.before) > .01) throw Error("Keyboard nudge or undo was not exercised correctly: " + JSON.stringify(row));
    rows.push(row);
  }
  const profile = (await cdp.send("Profiler.stop")).profile;
  const nodes = new Map(profile.nodes.map(node => [node.id, node.callFrame]));
  const totals = new Map();
  for (let i = 0; i < (profile.samples || []).length; i++) {
    const frame = nodes.get(profile.samples[i]);
    const name = `${frame.functionName || "anonymous"} ${frame.url.split("/").pop()}:${frame.lineNumber + 1}`;
    totals.set(name, (totals.get(name) || 0) + (profile.timeDeltas[i] || 0) / 1000);
  }
  fs.writeFileSync(path.join(output, "dense-commands.cpuprofile"), JSON.stringify(profile));
  await cdp.detach();
  await page.evaluate(async () => { await flushPendingAutosave(); });
  return { rows, topCpu: [...totals].sort((a, b) => b[1] - a[1]).slice(0, 30) };
}
