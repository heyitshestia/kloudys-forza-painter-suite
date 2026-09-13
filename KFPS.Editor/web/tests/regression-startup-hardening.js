async (page) => {
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const first = await page.evaluate(async () => {
    const original = requestAnimationFrame;
    window.requestAnimationFrame = () => 0;
    const yields = await Promise.race([nextFrame().then(() => true), new Promise(r => setTimeout(() => r(false), 1200))]);
    window.requestAnimationFrame = original;
    const shapes = Array.from({length: 3000}, (_, i) => ({type: 1048677, color: [24, 145, 190, 255], data: [(i % 60) * 25 - 750, Math.floor(i / 60) * 25 - 600, .1, .1, 0, 0, 0]}));
    await loadProjectPayload({name: 'Startup Regression', shapes}, 'Startup Regression');
    await saveProject();
    return { yields, saved: !documentDirty, count: vinylObjects().length };
  });
  check(first.yields && first.saved && first.count === 3000, 'Initial project save/yield failed');
  // Cold document startup, not loadProjectPayload in an already initialized canvas.
  const url = await page.evaluate(() => location.origin + location.pathname);
  await page.goto(url + '?project=Startup%20Regression.fabric-project.json&lang=ko');
  await page.waitForFunction(() => window.KfpsDesktop?.ready && vinylObjects().length === 3000, null, {timeout: 60000});
  const cold = await page.evaluate(() => ({count: vinylObjects().length, name: currentProjectName, language: KfpsI18n.locale, busy: !$('busyBanner').hidden}));
  check(cold.name === 'Startup Regression' && !cold.busy, 'Cold Korean project startup failed');
  await page.screenshot({path: 'cold-project-korean.png'});
  const worker = page.workers().find(item => item.url().includes('editor-persistence-worker'));
  check(worker, 'Actual project persistence worker unavailable');
  await worker.evaluate(() => {
    self.originalFetch = fetch;
    self.projectReadDeadline = false;
    self.fetch = async (url, options) => {
      if (String(url).includes('/project-file?')) {
        self.projectReadDeadline = Boolean(options?.signal);
        return new Response('{invalid', {status: 200});
      }
      return originalFetch(url, options);
    };
  });
  const failures = await page.evaluate(async () => {
    const before = JSON.stringify(vinylObjects().map(o => objectToShape(o, {includeEditorMeta: true})));
    const loaded = await loadStartupProjectFromQuery();
    const preserved = before === JSON.stringify(vinylObjects().map(o => objectToShape(o, {includeEditorMeta: true})));
    $('messageDialog').close();
    return {loaded, preserved};
  });
  failures.deadline = await worker.evaluate(() => { self.fetch = originalFetch; return projectReadDeadline; });
  Object.assign(failures, await page.evaluate(async () => {
    const bitmap = document.createElement('canvas'); bitmap.width = bitmap.height = 8;
    bitmap.getContext('2d').fillRect(0, 0, 8, 8);
    const originalAdd = canvas.add;
    canvas.add = function(object) { if (object.kloudyOverlay) throw new Error('Injected reference install failure'); return originalAdd.call(this, object); };
    const rejected = await Promise.race([
      editorReference.loadOverlayImageFromUrl(bitmap.toDataURL(), 'fault.png').then(() => false, () => true),
      new Promise(r => setTimeout(() => r(false), 1200)),
    ]);
    canvas.add = originalAdd;
    editorReference.clearSourceOverlayState();
    await loadStartupProjectFromQuery();
    return {rejected, retryCount: vinylObjects().length, busy: !$('busyBanner').hidden};
  }));
  check(failures.deadline && !failures.loaded && failures.preserved && failures.rejected && failures.retryCount === 3000 && !failures.busy, 'Load failure/retry contract failed: ' + JSON.stringify(failures));
  // Browser storage denial must not stop the script before controls are bound.
  await page.addInitScript(() => {
    const get = Storage.prototype.getItem, set = Storage.prototype.setItem;
    Storage.prototype.getItem = function(key) { if (this === localStorage) throw new DOMException('Injected storage denial', 'SecurityError'); return get.call(this, key); };
    Storage.prototype.setItem = function(key, value) { if (this === localStorage) throw new DOMException('Injected quota', 'QuotaExceededError'); return set.call(this, key, value); };
  });
  await page.goto(url + '?lang=ko');
  await page.waitForFunction(() => window.KfpsDesktop?.ready, null, {timeout: 60000});
  await page.locator('[data-tool-mode="shapeLibrary"]').click();
  await page.waitForFunction(() => activeToolMode === 'shapeLibrary');
  const storageDenied = await page.evaluate(async () => {
    await loadPayload({shapes: [{type: 1048677, color: [255,255,255,255], data: [0,0,1,1,0,0,0]}]});
    return {count: vinylObjects().length, ready: KfpsDesktop.ready};
  });
  check(storageDenied.ready && storageDenied.count === 1, 'Storage denial disabled controls or resource loading');
  return {first, cold, failures, storageDenied};
}
