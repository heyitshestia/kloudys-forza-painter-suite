async (page, options) => {
  const cdp = await page.context().newCDPSession(page);
  const files = [null, "reference-small.png", "reference-noise-24mp.png"];
  const results = [];
  await page.evaluate(() => {
    window.referenceProbe = { frames: [], tasks: [], running: true };
    referenceProbe.observer = new PerformanceObserver(list => {
      referenceProbe.tasks.push(...list.getEntries().map(entry => ({ at: entry.startTime, duration: entry.duration })));
      if (referenceProbe.tasks.length > 2000) referenceProbe.tasks.splice(0, referenceProbe.tasks.length - 2000);
    });
    referenceProbe.observer.observe({ type: "longtask" });
    let previous = performance.now();
    const frame = now => {
      referenceProbe.frames.push({ at: now, duration: now - previous }); previous = now;
      if (referenceProbe.frames.length > 10000) referenceProbe.frames.shift();
      if (referenceProbe.running) referenceProbe.frame = requestAnimationFrame(frame);
    };
    referenceProbe.frame = requestAnimationFrame(frame);
  });
  const timed = async (name, action) => {
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const at = await page.evaluate(() => performance.now()), utcStart = Date.now();
    await action();
    const utcEnd = Date.now();
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    return page.evaluate(({ at, name, utcStart, utcEnd }) => {
      const frames = referenceProbe.frames.filter(row => row.at >= at).map(row => row.duration).sort((a, b) => a - b);
      const tasks = referenceProbe.tasks.filter(row => row.at >= at).map(row => row.duration);
      return { name, utcStart, utcEnd, wallMs: utcEnd - utcStart, frames: frames.length,
        frameP95: frames[Math.floor(frames.length * .95)] || 0, frameMax: Math.max(0, ...frames),
        gaps100: frames.filter(value => value >= 100).length, taskMax: Math.max(0, ...tasks) };
    }, { at, name, utcStart, utcEnd });
  };
  try {
    for (const file of files) {
      await page.evaluate(async () => {
        await flushPendingAutosave();
        await loadPayload({ shapes: Array.from({ length: 3000 }, (_, index) => ({ type: 1048677,
          data: [-700 + index % 60 * 24, 600 - Math.floor(index / 60) * 24, .18, .18, 0, 0, 0], color: [40 + index % 170, 150, 210, 255] })) }, { projectName: null });
        fitDesignView(); await flushPendingAutosave();
      });
      const operations = [];
      if (file) {
        await cdp.send("Profiler.enable"); await cdp.send("Profiler.start");
        operations.push(await timed("reference-load", async () => {
          const { root } = await cdp.send("DOM.getDocument");
          const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector: "#overlayInput" });
          await cdp.send("DOM.setFileInputFiles", { nodeId, files: [path.join(options.fixtures, file)] });
          await page.waitForFunction(name => editorReference.source?.fileName === name, file);
        }));
        fs.writeFileSync(path.join(output, `${file}.cpuprofile`), JSON.stringify((await cdp.send("Profiler.stop")).profile));
        await page.evaluate(() => flushPendingAutosave());
      }
      await page.evaluate(name => { currentProjectName = name; }, `Reference benchmark ${file || "none"}`);
      for (let repeat = 0; repeat < 3; repeat++) {
        operations.push(await timed("save", () => page.evaluate(async () => {
          await saveProject(); if (isDocumentDirty()) throw Error("Save did not complete");
          await flushPendingAutosave();
        })));
        operations.push(await timed("held-nudge-and-recovery", () => page.evaluate(async () => {
          selectObjects(vinylObjects().slice(0, 40), "storage test");
          for (let step = 0; step < 20; step++) { nudgeSelected(1, 0); await new Promise(resolve => setTimeout(resolve, 80)); }
          flushPendingNudgeHistory(); await flushPendingAutosave();
          if (!editorRecovery.status.serverOk || !editorRecovery.status.browserOk) throw Error("Recovery not acknowledged");
        })));
        await page.evaluate(async () => {
          const saved = await readAutosavePayload();
          if (JSON.stringify(saved.shapes) !== JSON.stringify(snapshotShapes()) || (saved.editor_source_overlay?.data_url || null) !== (editorReference.source?.dataUrl || null)) throw Error("Readback changed artwork or reference");
        });
      }
      results.push({ file, operations });
      fs.writeFileSync(path.join(output, "reference-storage.json"), JSON.stringify(results, null, 2));
    }
    return results;
  } finally {
    await cdp.detach();
    await page.evaluate(async () => {
      referenceProbe.running = false; referenceProbe.observer.disconnect(); cancelAnimationFrame(referenceProbe.frame);
      await flushPendingAutosave();
    });
  }
}
