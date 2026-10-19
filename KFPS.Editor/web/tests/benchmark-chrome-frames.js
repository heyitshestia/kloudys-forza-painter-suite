async (page, options = {}) => {
  const count = options.count || 300;
  const samples = options.samples || 12;
  const viewport = { width: options.width || 1600, height: options.height || 1000 };
  if (!options.browserHost) throw Error('This benchmark requires the real Chrome BrowserDesktop harness');
  if (![300, 3000].includes(count) || !Number.isInteger(samples) || samples < 3 || samples > 30) {
    throw Error('Use 300 or 3000 layers and 3-30 bounded samples');
  }
  const tests = path.join(process.env.KFPS_TEST_APP_ROOT, 'KFPS.Editor/web/tests');
  const { summarize, inspectPixels } = require(path.join(tests, 'chrome-frame-metrics.cjs'));
  const save = (name, data) => fs.writeFileSync(path.join(output, name), JSON.stringify(data, null, 2));
  const dependencies = ['regression-chrome-save-roundtrip.js', 'chrome-frame-metrics.cjs'];
  const inputs = path.join(output, 'test-inputs');
  fs.mkdirSync(inputs, { recursive: true });
  const sources = {};
  for (const name of dependencies) {
    sources[name] = fs.readFileSync(path.join(tests, name), 'utf8');
    fs.writeFileSync(path.join(inputs, name), sources[name]);
    save('test-inputs/' + name + '.json', { sha256: crypto.createHash('sha256').update(sources[name]).digest('hex') });
  }
  const contract = {
    scene: { count, complex: !!options.complex, samples, viewport },
    fixture: 'Same deterministic run-15 grid/families/colors/masks, initialized without retired cache hooks or dispatch timing',
    hybrid: 'hybridRenderNow plus gl.finish: CPU submission and GPU command completion, not display presentation',
    settled: 'Intrusive diagnostic after pointer timing: Fabric renderAll plus full getImageData, including readback cost',
    pointer: 'Actual mouse move, two RAF callbacks, gl.finish; includes automation/CDP/scheduling overhead',
    instrumentation: 'Draw-call and object-render counters only; timings include their overhead',
    exclusions: ['No hardware-visible FPS claim', 'No comparison against Qt software renderer',
      'No raw page reload certification', 'No performance improvement claim', 'No driver/settings changes'],
  };
  save('measurement-contract.json', contract);
  const network = [], consoleErrors = [];
  const failed = request => network.push({ url: request.url(), method: request.method(), failure: request.failure() });
  const consoleMessage = message => {
    if (message.type() === 'error') consoleErrors.push({ text: message.text(), location: message.location() });
  };
  page.on('requestfailed', failed);
  page.on('console', consoleMessage);
  page.setDefaultTimeout(30000);
  page.setDefaultNavigationTimeout(30000);
  let pointerDown = false;
  const progress = stage => save('chrome-benchmark-progress.json', { stage, at: new Date().toISOString() });
  const pixelEvidence = async mode => {
    const result = await page.evaluate(({ mode, inspectSource }) => {
      const inspect = eval(`(${inspectSource})`);
      if (mode === 'hybrid') {
        if (!editorRenderer.active || !editorRenderer.hybridRenderNow()) throw Error('Hybrid scene did not render');
        const { gl, element } = editorRenderer.renderer;
        const pixels = new Uint8Array(element.width * element.height * 4);
        gl.readPixels(0, 0, element.width, element.height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        if (gl.getError() !== gl.NO_ERROR) throw Error('Hybrid pixel readback failed');
        return inspect(pixels);
      }
      if (editorRenderer.active) throw Error('Fabric pixel check must use the settled scene');
      canvas.renderAll();
      return inspect(canvas.contextContainer.getImageData(0, 0, canvas.lowerCanvasEl.width, canvas.lowerCanvasEl.height).data);
    }, { mode, inspectSource: inspectPixels.toString() });
    save(mode + '-pixels.json', result);
    if (!result.nonblank) throw Error(mode + ' scene pixels were blank or insufficiently varied');
    await page.screenshot({ path: path.join(output, mode + '-scene.png'), timeout: 15000 });
    return result;
  };
  try {
    await page.setViewportSize(viewport);
    progress('fixture');
    const setup = await page.evaluate(async ({ count, complex }) => {
      const slots = [1, 2, 30, 36, 39, 31, 12, 5];
      const cols = Math.ceil(Math.sqrt(count * 1.5)), rows = Math.ceil(count / cols);
      const shapes = Array.from({ length: count }, (_, i) => {
        const gradient = i % 17 === 8;
        const family = gradient ? 'Gradient_Shapes' : complex ?
          ['Tribal', 'Nature', 'Tears', 'Flames', 'Paint_Splats', 'Racing_Icons', 'Upper_Letters_1', 'Primitives'][Math.floor(i / slots.length) % 8] : 'Primitives';
        const slot = gradient ? 1 : slots[i % slots.length], mask = i > 0 && i % 53 === 0;
        return { type: editorCatalog.resourceToTypeCode(family, slot), resource_family: family, resource_index: slot,
          editor_id: `perf-${i}`, shape_name: `Performance ${i}`,
          color: [45 + i * 37 % 190, 40 + i * 73 % 190, 50 + i * 23 % 180, i % 3 ? 255 : 151], mask,
          data: [(i % cols - (cols - 1) / 2) * 38, (Math.floor(i / cols) - (rows - 1) / 2) * 38,
            (i % 7 ? 1 : -1) * .4, .32 + i % 4 * .04, i % 6 * 17, 0, mask ? 1 : 0] };
      });
      const started = performance.now();
      await loadPayload({ shapes });
      const loadMs = performance.now() - started;
      const zoom = Math.min((canvas.width - 80) / (cols * 38 + 100), (canvas.height - 80) / (rows * 38 + 100));
      canvas.setViewportTransform([zoom, 0, 0, zoom, canvas.width / 2, canvas.height / 2]);
      const objects = vinylObjects();
      if (objects.length !== count) throw Error('Fixture layer count mismatch');
      if (objects.some(object => object.type === 'path' && object.drawCacheOnCanvas !== fabric.Object.prototype.drawCacheOnCanvas)) {
        throw Error('Fixture must retain the frozen Fabric cache drawing contract');
      }
      return { count, loadMs, zoom, canvas: [canvas.width, canvas.height], dpr: devicePixelRatio,
        pathCommands: objects.reduce((n, object) => n + (object.path?.length || 0), 0),
        maxPathCommands: Math.max(...objects.map(object => object.path?.length || 0)),
        masks: objects.filter(object => object.kloudy.mask).length,
        images: objects.filter(object => object.type === 'image').length,
        visible: objects.filter(object => object.isOnScreen()).length };
    }, { count, complex: !!options.complex });
    save('setup.json', setup);
    await page.waitForFunction(() => !editorRenderer.warmingDocument && !editorRenderer.active, null, { timeout: 45000 });
    await page.evaluate(() => {
      window.chromeFrameAudit = { draws: 0, moving: 0, lastDrawMoving: 0, objectDraws: 0 };
      const gl = editorRenderer.renderer?.gl;
      if (!gl) throw Error('Chrome benchmark requires an actual hybrid WebGL context');
      const originalDraw = gl.drawArrays;
      const extension = editorRenderer.renderer.instanced?.extension;
      const originalInstanced = extension?.drawArraysInstancedANGLE;
      const originalObjectRender = fabric.Object.prototype.render;
      const recordDraw = () => {
        chromeFrameAudit.draws++;
        chromeFrameAudit.lastDrawMoving = chromeFrameAudit.moving;
      };
      chromeFrameAudit.restore = () => {
        gl.drawArrays = originalDraw;
        if (extension) extension.drawArraysInstancedANGLE = originalInstanced;
        fabric.Object.prototype.render = originalObjectRender;
      };
      fabric.Object.prototype.render = function (...args) {
        chromeFrameAudit.objectDraws++;
        return originalObjectRender.apply(this, args);
      };
      gl.drawArrays = function (...args) {
        recordDraw();
        return originalDraw.apply(this, args);
      };
      if (extension) extension.drawArraysInstancedANGLE = function (...args) {
        recordDraw();
        return originalInstanced.apply(this, args);
      };
      window.chromeMoveObserver = () => { chromeFrameAudit.moving++; };
      canvas.on('object:moving', chromeMoveObserver);
    });

    progress('hybrid-completion');
    await page.evaluate(() => {
      if (!editorRenderer.beginHybridRender('Chrome benchmark')) throw Error('Hybrid renderer declined the scene');
    });
    await page.waitForFunction(() => editorRenderer.active && !editorRenderer.renderer.element.hidden);
    const hybrid = [];
    for (let i = 0; i < samples + 2; i++) {
      const result = await page.evaluate(() => {
        const { gl } = editorRenderer.renderer;
        gl.finish();
        const before = chromeFrameAudit.draws;
        const start = performance.now();
        if (!editorRenderer.hybridRenderNow()) throw Error('Hybrid renderer fell back during measurement');
        gl.finish();
        const ms = performance.now() - start;
        if (gl.isContextLost() || gl.getError() !== gl.NO_ERROR) throw Error('WebGL completion failed');
        if (chromeFrameAudit.draws === before) throw Error('Hybrid sample drew no geometry');
        return { ms, drawCalls: chromeFrameAudit.draws - before };
      });
      if (i >= 2) hybrid.push(result);
    }
    save('hybrid-completion.json', { metric: contract.hybrid, warmups: 2, rows: hybrid,
      summary: summarize(hybrid.map(row => row.ms)) });
    const hybridPixels = await pixelEvidence('hybrid');

    progress('real-pointer-completion');
    const center = await page.evaluate(() => {
      editorRenderer.endHybridRenderNow();
      canvas.cancelRequestedRender();
      selectObjects(vinylObjects().filter(object => !object.kloudy.mask), 'Chrome frame benchmark');
      canvas.renderAll();
      window.chromeBefore = JSON.stringify(snapshotShapes());
      const point = fabric.util.transformPoint(canvas.getActiveObject().getCenterPoint(), canvas.viewportTransform);
      const rect = canvas.upperCanvasEl.getBoundingClientRect();
      return { x: rect.left + point.x, y: rect.top + point.y };
    });
    const pointer = [];
    await page.mouse.move(center.x, center.y);
    await page.mouse.down();
    pointerDown = true;
    for (let i = 1; i <= samples; i++) {
      const before = await page.evaluate(() => ({ draws: chromeFrameAudit.draws, moving: chromeFrameAudit.moving }));
      const started = performance.now();
      await page.mouse.move(center.x + i * 4, center.y + i * 3);
      const state = await page.evaluate(async before => {
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const { gl, element } = editorRenderer.renderer;
        gl.finish();
        if (!editorRenderer.active || element.hidden || gl.isContextLost() || gl.getError() !== gl.NO_ERROR) {
          throw Error('Actual pointer step did not finish in the visible hybrid scene');
        }
        const draws = chromeFrameAudit.draws - before.draws;
        const moving = chromeFrameAudit.moving - before.moving;
        if (!draws || !moving || chromeFrameAudit.lastDrawMoving !== chromeFrameAudit.moving) {
          throw Error('Pointer step lacked a completed draw of the latest actual move');
        }
        return { draws, moving };
      }, before);
      pointer.push({ ms: performance.now() - started, ...state });
      save('pointer-completion-progress.json', pointer);
    }
    await page.screenshot({ path: path.join(output, 'pointer-drag-scene.png'), timeout: 15000 });
    await page.mouse.up();
    pointerDown = false;
    const pointerSummary = summarize(pointer.map(row => row.ms));
    save('pointer-completion.json', { metric: contract.pointer, rows: pointer, summary: pointerSummary });
    const correctness = await page.evaluate(async () => {
      const after = JSON.stringify(snapshotShapes());
      if (after === chromeBefore || !chromeFrameAudit.moving) throw Error('Pointer did not change artwork');
      await undo();
      if (JSON.stringify(snapshotShapes()) !== chromeBefore) throw Error('Pointer undo mismatch');
      await redo();
      if (JSON.stringify(snapshotShapes()) !== after) throw Error('Pointer redo mismatch');
      return { exactUndo: true, exactRedo: true, movedEvents: chromeFrameAudit.moving,
        layers: vinylObjects().length, selected: selectedVinylObjects().length };
    });
    save('pointer-correctness.json', correctness);

    // Repeated Canvas2D readback may influence acceleration heuristics. Keep it
    // after all interaction timing and never report it as normal-frame latency.
    progress('settled-raster-readback');
    await page.evaluate(() => { editorRenderer.endHybridRenderNow(); canvas.cancelRequestedRender(); });
    const settled = [];
    for (let i = 0; i < samples + 2; i++) {
      const result = await page.evaluate(() => {
        if (editorRenderer.active) throw Error('Fabric dispatch cannot be measured as a completed frame');
        const before = chromeFrameAudit.objectDraws;
        canvas.cancelRequestedRender();
        const start = performance.now();
        canvas.renderAll();
        const rgba = canvas.contextContainer.getImageData(0, 0, canvas.lowerCanvasEl.width, canvas.lowerCanvasEl.height);
        const ms = performance.now() - start;
        const objectCalls = chromeFrameAudit.objectDraws - before;
        if (!objectCalls || !rgba.data.length) throw Error('Settled sample did not draw/read the actual scene');
        return { ms, objectCalls, rgbaBytes: rgba.data.length };
      });
      if (i >= 2) settled.push(result);
    }
    save('settled-raster-readback.json', { metric: contract.settled, warmups: 2, rows: settled,
      summary: summarize(settled.map(row => row.ms)) });
    const settledPixels = await pixelEvidence('settled');
    progress('disk-save-export-picker-reopen');
    const roundtrip = await eval(`(${sources['regression-chrome-save-roundtrip.js']})`)(page);
    await page.waitForFunction(() => !editorRenderer.warmingDocument && !editorRenderer.active, null, { timeout: 45000 });
    await page.screenshot({ path: path.join(output, 'reopened-settled-scene.png'), timeout: 15000 });
    const sourceSession = await page.context().newCDPSession(page);
    const expectedAssets = JSON.parse(fs.readFileSync(path.join(output, 'asset-readback.json'), 'utf8'));
    const parsed = new Map(), readback = [];
    sourceSession.on('Debugger.scriptParsed', entry => {
      const name = entry.url.split('/').pop().split('?')[0];
      if (expectedAssets.some(asset => asset.name === name)) parsed.set(name, entry.scriptId);
    });
    try {
      await sourceSession.send('Debugger.enable');
      for (const asset of expectedAssets) {
        if (!parsed.has(asset.name)) throw Error('Final renderer did not parse ' + asset.name);
        const { scriptSource } = await sourceSession.send('Debugger.getScriptSource', { scriptId: parsed.get(asset.name) });
        const actual = crypto.createHash('sha256').update(scriptSource).digest('hex');
        const disk = crypto.createHash('sha256').update(fs.readFileSync(path.join(tests, '..', asset.name))).digest('hex');
        readback.push({ name: asset.name, actual, disk, expected: asset.expected,
          matched: actual === asset.expected && disk === actual });
        if (!readback.at(-1).matched) throw Error('Source changed during benchmark: ' + asset.name);
      }
    } finally {
      save('asset-readback-end.json', readback);
      await sourceSession.send('Debugger.disable');
      await sourceSession.detach();
    }
    if (network.some(entry => /\.js(?:\?|$)/.test(entry.url))) throw Error('JavaScript resource failed during benchmark');
    progress('complete');
    return { passed: true, count, setup, contract, hybridPixels, settledPixels,
      hybrid: summarize(hybrid.map(row => row.ms)), settled: summarize(settled.map(row => row.ms)),
      pointer: pointerSummary, correctness, roundtrip };
  } catch (error) {
    save('chrome-benchmark-failure.json', { error: String(error.stack || error), network, consoleErrors });
    await page.screenshot({ path: path.join(output, 'chrome-benchmark-failure.png'), timeout: 10000 }).catch(() => {});
    throw error;
  } finally {
    if (pointerDown) await page.mouse.up().catch(() => {});
    await page.evaluate(() => {
      window.chromeFrameAudit?.restore?.();
      if (window.chromeMoveObserver) canvas.off('object:moving', chromeMoveObserver);
    }).catch(() => {});
    save('chrome-network-errors.json', network);
    save('chrome-console-errors.json', consoleErrors);
    page.removeListener('requestfailed', failed);
    page.removeListener('console', consoleMessage);
    page.setDefaultTimeout(120000);
    page.setDefaultNavigationTimeout(120000);
  }
}
