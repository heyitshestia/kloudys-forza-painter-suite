async page => {
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const edit = () => page.evaluate(() => {
    const object = vinylObjects()[0];
    object.left += 7; object.setCoords(); pushHistory("persistence fault test");
    return objectToShape(object, { includeEditorMeta: true }).data[0];
  });
  const status = () => page.evaluate(() => editorRecovery.status);
  const flush = () => page.evaluate(() => flushPendingAutosave());
  const checks = [];
  await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: [{ type: 1048677, color: [20, 90, 210, 255], data: [64, 0, 1, 1, 0, 0, 0] }] });
    await flushPendingAutosave();
  });
  let worker = page.workers().find(item => item.url().includes("editor-persistence-worker"));
  assert(worker, "Actual persistence worker not available");
  await worker.evaluate(() => {
    self.originalFetch = fetch;
    self.originalTransaction = IDBDatabase.prototype.transaction;
    self.fault = { mode: "", entered: false, requests: 0, active: 0, maxActive: 0, writes: [] };
    self.fetch = async (url, options) => {
      const write = url === "/api/fabric-editor/autosave" && options?.method === "POST";
      if (!write && fault.mode === "read-timeout" && String(url).includes("autosave?compact")) {
        return new Promise((resolve, reject) => options.signal.addEventListener("abort", () => reject(options.signal.reason), { once: true }));
      }
      if (!write) return originalFetch(url, options);
      fault.requests++;
      fault.active++; fault.maxActive = Math.max(fault.maxActive, fault.active);
      fault.writes.push({ revision: JSON.parse(options.body).recovery_revision, time: Date.now() });
      try {
        if (fault.mode === "hold") {
          fault.mode = ""; fault.entered = true;
          await new Promise(resolve => { self.releaseWrite = resolve; });
        }
        if (fault.mode === "http") return new Response("unavailable", { status: 503 });
        if (fault.mode === "http-once") { fault.mode = ""; return new Response("unavailable", { status: 503 }); }
        const response = await originalFetch(url, options);
        if (fault.mode === "lost-ack") { fault.mode = ""; throw new TypeError("Response lost after durable commit"); }
        return response;
      } finally { fault.active--; }
    };
  });
  try {
    const began = Date.now();
    await worker.evaluate(() => { fault.writes = []; });
    for (let index = 0; index < 32; index++) { await edit(); await new Promise(resolve => setTimeout(resolve, 100)); }
    await page.waitForFunction(() => editorRecovery.status.serverOk === true);
    const cadence = await worker.evaluate(() => fault.writes);
    assert(cadence.length >= 2 && cadence[0].time - began < 2600, "Continuous editing starved recovery");
    checks.push({ continuousFirstWriteMs: cadence[0].time - began, writes: cadence.length });

    await worker.evaluate(() => { fault.mode = "lost-ack"; });
    await edit(); await flush();
    assert(!(await status()).serverOk, "Lost ACK did not exercise failure");
    await page.waitForFunction(() => editorRecovery.status.serverOk === true);
    checks.push("durable commit with lost response acknowledged on retry");

    await worker.evaluate(() => { fault.mode = "read-timeout"; });
    const beforeRead = Date.now();
    const fallback = await page.evaluate(() => readAutosavePayload());
    const readMs = Date.now() - beforeRead;
    assert(fallback?.shapes.length === 1 && readMs >= 4900 && readMs < 6500, "Read timeout did not preserve browser fallback");
    checks.push({ readTimeoutFallbackMs: readMs });

    await worker.evaluate(() => { fault.mode = "hold"; fault.entered = false; fault.maxActive = 0; fault.requests = 0; });
    await edit();
    await page.evaluate(() => { window.heldRecovery = flushPendingAutosave(); });
    for (let i = 0; i < 50 && !await worker.evaluate(() => fault.entered); i++) await new Promise(resolve => setTimeout(resolve, 20));
    assert(await worker.evaluate(() => fault.entered), "Server hold never reached");
    await page.evaluate(() => { void clearAutosave(); });
    let newestX;
    for (let i = 0; i < 12; i++) newestX = await edit();
    await new Promise(resolve => setTimeout(resolve, 850));
    const browser = await worker.evaluate(() => browserRead());
    assert(browser[0]?.payload.shapes[0].data[0] === newestX, "Stalled server prevented latest browser checkpoint");
    assert((await status()).browserOk && !(await status()).serverOk, "Pending server concealed browser-only recovery");
    await worker.evaluate(() => releaseWrite());
    await page.evaluate(() => heldRecovery);
    const exact = await page.evaluate(async () => (await readAutosavePayload()).shapes[0].data[0]);
    const ordering = await worker.evaluate(() => ({ requests: fault.requests, maxActive: fault.maxActive }));
    assert(exact === newestX && ordering.maxActive === 1 && ordering.requests === 2, "Stalled write violated ordering/coalescing");
    checks.push({ independentBrowserBackup: true, ...ordering });

    await worker.evaluate(() => {
      fault.mode = "http";
      IDBDatabase.prototype.transaction = function(...args) {
        if (args[1] === "readwrite") throw new DOMException("Synthetic quota failure", "QuotaExceededError");
        return originalTransaction.apply(this, args);
      };
    });
    await edit(); await flush();
    assert((await status()).state === "failed", "Dual disk/browser failure reported saved");
    await worker.evaluate(() => { fault.mode = ""; });
    await edit(); await flush();
    assert((await status()).serverOk && !(await status()).browserOk, "App-folder recovery did not survive browser quota failure");
    checks.push("dual failure visible; quota failure retains app-folder recovery");
    await worker.evaluate(() => { IDBDatabase.prototype.transaction = originalTransaction; fault.mode = "http-once"; });
    await edit(); await flush();
    assert((await status()).browserOk && !(await status()).serverOk, "HTTP failure did not retain browser recovery");
    await page.waitForFunction(() => editorRecovery.status.serverOk === true);
    checks.push("HTTP retry without another edit");

    await worker.evaluate(() => {
      self.onmessage = () => { setTimeout(() => { throw new Error("Synthetic worker crash"); }, 0); };
    });
    await edit(); await flush();
    assert((await status()).state === "failed", "Worker crash was called saved");
    await page.waitForFunction(() => editorRecovery.status.serverOk === true);
    worker = page.workers().find(item => item.url().includes("editor-persistence-worker"));
    assert(worker, "Worker did not restart");
    checks.push("worker crash recreated worker and retried latest checkpoint");

    await page.evaluate(async () => {
      const old = await readAutosavePayload();
      await clearAutosave();
      localStorage.setItem(AUTOSAVE_KEY, JSON.stringify(old));
      if (await readAutosavePayload() !== null) throw new Error("Clear resurrected older legacy recovery");
      const response = await fetch(EDITOR_AUTOSAVE_API, { method: "POST", headers: { ...EDITOR_MUTATION_HEADERS, "Content-Type": "application/json" }, body: JSON.stringify({ shapes: old.shapes }) });
      if ((await response.json()).applied !== false) throw new Error("Unversioned write bypassed revision watermark");
    });
    checks.push("clear tombstone rejects stale local and unversioned server writes");
    return { passed: true, checks };
  } finally {
    if (worker) await worker.evaluate(() => {
      self.releaseWrite?.();
      if (self.originalFetch) self.fetch = originalFetch;
      if (self.originalTransaction) IDBDatabase.prototype.transaction = originalTransaction;
    }).catch(() => {});
    await page.evaluate(async () => { await clearAutosave(); documentDirty = false; });
  }
}
