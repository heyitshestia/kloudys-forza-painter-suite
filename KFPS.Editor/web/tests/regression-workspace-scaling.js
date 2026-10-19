async (page, options = {}) => {
  const fs = require('node:fs');
  const crypto = require('node:crypto');
  const appRoot = process.env.KFPS_TEST_APP_ROOT || path.resolve(__dirname, '../../..');
  const webRoot = path.join(appRoot, 'KFPS.Editor/web');
  const processInfo = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
  const hash = value => crypto.createHash('sha256').update(value).digest('hex');
  const check = (condition, message) => { if (!condition) throw Error(message); };
  const report = {
    platform: process.platform, qtPlatform: process.env.QT_QPA_PLATFORM,
    requestedScale: Number(process.env.QT_SCALE_FACTOR), process: processInfo,
    rendering: 'Qt offscreen with GPU disabled; no physical-monitor or physical-GPU qualification',
    viewportPolicy: 'Run existing suites with unchanged Playwright resizing; distinguish measured browser DPR from native Qt scaling',
    lookback: 'Calibration found Qt scaling consistent, but browser startup DPR differed between runs and could remain at 1 after ten seconds. Disabling the driver DPR override did not give a reliable qualification path. Keep the existing suites unchanged, record actual metrics, and fail DPI qualification explicitly instead of synthesizing the expected ratio.',
    viewports: [], suites: [], screenshots: [], layouts: [], identities: [], qualificationGaps: [],
  };
  const writeReport = () => fs.writeFileSync(path.join(output, 'workspace-scaling-report.json'), JSON.stringify(report, null, 2));
  const session = await page.context().newCDPSession(page);
  const metrics = () => page.evaluate(() => ({
    width: innerWidth, height: innerHeight, devicePixelRatio,
    screenWidth: screen.width, screenHeight: screen.height,
    visualViewportScale: visualViewport?.scale,
  }));
  page.setDefaultTimeout(20000);

  async function sourceIdentity(stage) {
    const assets = ['editor-workspace.js', 'workspace.css'];
    const parsed = new Map(), styles = new Map();
    const scriptListener = entry => {
      if (entry.url.split('?')[0].endsWith('/editor-workspace.js')) parsed.set('editor-workspace.js', entry.scriptId);
    };
    const styleListener = ({ header }) => {
      if (header.sourceURL.split('?')[0].endsWith('/workspace.css')) styles.set('workspace.css', header.styleSheetId);
    };
    session.on('Debugger.scriptParsed', scriptListener);
    session.on('CSS.styleSheetAdded', styleListener);
    try {
      await session.send('Debugger.enable');
      await session.send('DOM.enable');
      await session.send('CSS.enable');
      for (const name of assets) {
        check(name.endsWith('.css') ? styles.has(name) : parsed.has(name), `Loaded source missing: ${name}`);
        const source = name.endsWith('.css')
          ? (await session.send('CSS.getStyleSheetText', { styleSheetId: styles.get(name) })).text
          : (await session.send('Debugger.getScriptSource', { scriptId: parsed.get(name) })).scriptSource;
        const disk = fs.readFileSync(path.join(webRoot, name), 'utf8');
        const item = { stage, name, expected: hash(disk), actual: hash(source), matched: disk === source };
        report.identities.push(item);
        check(item.matched, `Stale or concurrently changed ${name}: ${stage}`);
        const destination = path.join(output, 'workspace-sources', name);
        fs.mkdirSync(path.dirname(destination), { recursive: true });
        fs.writeFileSync(destination, source);
      }
    } finally {
      await session.send('CSS.disable');
      await session.send('DOM.disable');
      await session.send('Debugger.disable');
      session.off('Debugger.scriptParsed', scriptListener);
      session.off('CSS.styleSheetAdded', styleListener);
    }
  }

  async function screenshot(name) {
    const actual = await metrics();
    const png = await page.screenshot({ path: path.join(output, name), scale: 'device' });
    check(png.toString('ascii', 1, 4) === 'PNG', `${name}: expected PNG evidence`);
    const size = { width: png.readUInt32BE(16), height: png.readUInt32BE(20) };
    report.screenshots.push({ name, css: actual, pixels: size });
    check(Math.abs(size.width - actual.width * actual.devicePixelRatio) <= 1 &&
      Math.abs(size.height - actual.height * actual.devicePixelRatio) <= 1, `${name}: screenshot lost native pixel density`);
  }

  try {
    check(process.platform === 'win32', 'Scaling qualification requires the real Windows native host');
    check(process.env.QT_QPA_PLATFORM === 'offscreen', 'Scaling suite must remain offscreen');
    check(process.env.QTWEBENGINE_CHROMIUM_FLAGS?.includes('--disable-gpu'), 'Scaling suite requires the isolated software-rendering environment');
    check([1.25, 1.5, 2].includes(report.requestedScale), 'Set QT_SCALE_FACTOR to 1.25, 1.5, or 2');
    check(Number(processInfo.qtScaleFactor) === report.requestedScale, 'Native host did not inherit the scale factor');
    await page.waitForFunction(() => window.KfpsDesktop?.ready && window.KfpsWorkspace);
    report.beforeClearingMetrics = await metrics();
    await session.send('Emulation.clearDeviceMetricsOverride');
    const screenInfo = processInfo.screens.find(screen => screen.name === processInfo.selectedScreen);
    check(screenInfo && Math.abs(screenInfo.dpr - report.requestedScale) < .01, 'Native Qt screen did not adopt the requested scale');
    report.native = await metrics();
    if (Math.abs(screenInfo.dpr - report.native.devicePixelRatio) >= .01) {
      report.qualificationGaps.push({ message: 'Native browser DPR does not match the scaled Qt screen',
        browser: report.native.devicePixelRatio, qt: screenInfo.dpr });
    }
    await sourceIdentity('startup');
    await screenshot('scaling-native-startup.png');

    // Observe, but do not change, the existing suites' viewport behavior. A
    // passing workflow is not DPI qualification when the actual ratios differ.
    const setViewportSize = async size => {
      await page.setViewportSize(size);
      const actual = await metrics();
      report.viewports.push({ requested: size, actual });
      check(actual.width === size.width && actual.height === size.height, `Viewport dimensions differ: ${JSON.stringify(actual)}`);
      if (Math.abs(actual.devicePixelRatio - screenInfo.dpr) >= .01 && !report.qualificationGaps.some(gap => gap.message === 'Suite viewport DPR does not match the scaled Qt screen')) {
        report.qualificationGaps.push({ message: 'Suite viewport DPR does not match the scaled Qt screen',
          browser: actual.devicePixelRatio, qt: screenInfo.dpr });
      }
      writeReport();
    };
    const scaledPage = new Proxy(page, {
      get(target, property) {
        if (property === 'setViewportSize') return setViewportSize;
        const value = Reflect.get(target, property, target);
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });
    for (const name of ['regression-workspace-shell.js', 'regression-workspace-baseline.js']) {
      const source = fs.readFileSync(path.join(__dirname, name), 'utf8');
      const destination = path.join(output, 'test-inputs', name);
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      fs.writeFileSync(destination, source);
      const run = eval(`(${source})`);
      const started = Date.now();
      const result = await run(scaledPage, options);
      check(result?.passed !== false, `${name} reported failure`);
      check(hash(fs.readFileSync(path.join(__dirname, name))) === hash(source), `${name} changed during the run`);
      report.suites.push({ name, sha256: hash(source), passed: true, ms: Date.now() - started, result, display: await metrics() });
      writeReport();
    }
    check(report.suites[1].result.layers === 240 && report.suites[1].result.saved, 'Baseline did not save the full 240-layer fixture');
    const pixels = await page.evaluate(() => {
      const element = canvas.lowerCanvasEl, context = element.getContext('2d');
      const data = context.getImageData(0, 0, element.width, element.height).data;
      const colors = new Set();
      for (let y = 0; y < element.height; y += Math.max(1, Math.floor(element.height / 80))) {
        for (let x = 0; x < element.width; x += Math.max(1, Math.floor(element.width / 80))) {
          const i = (y * element.width + x) * 4;
          if (data[i + 3]) colors.add(`${data[i]},${data[i + 1]},${data[i + 2]}`);
        }
      }
      return { backingWidth: element.width, backingHeight: element.height, sampledColors: colors.size };
    });
    report.canvas = pixels;
    check(pixels.sampledColors > 5, 'Scaled artwork canvas appears blank or unrendered');

    for (const size of [{ width: 1600, height: 1000 }, { width: 900, height: 640 }, { width: 760, height: 640 }]) {
      await setViewportSize(size);
      const layout = await page.evaluate(() => ({
        width: innerWidth, height: innerHeight, dpr: devicePixelRatio,
        overflow: document.documentElement.scrollWidth > innerWidth || document.documentElement.scrollHeight > innerHeight,
        controls: ['#workspaceZoomIn', '#workspaceZoomOut', '#workspaceFit', '#workspaceViewMenu', '#saveProject'].map(selector => {
          const node = document.querySelector(selector), r = node.getBoundingClientRect();
          const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
          return { selector, x: r.x, y: r.y, right: r.right, bottom: r.bottom,
            reachable: Boolean(hit && node.contains(hit)), interceptedBy: hit?.id || hit?.className };
        }),
      }));
      report.layouts.push(layout);
      check(!layout.overflow, `Scaled workspace overflows ${size.width}x${size.height}`);
      for (const control of layout.controls) {
        check(control.reachable && control.x >= 0 && control.y >= 0 && control.right <= size.width + 1 && control.bottom <= size.height + 1,
          `Scaled control clipped or occluded: ${JSON.stringify(control)}`);
      }
      await screenshot(`scaling-${size.width}-artwork.png`);
      await page.locator('#workspaceViewMenu').click();
      const menuFits = await page.locator('#workspaceViewCommands').evaluate(node => {
        const r = node.getBoundingClientRect();
        return r.x >= 0 && r.y >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1 && node.scrollWidth <= node.clientWidth + 1;
      });
      check(menuFits, `Scaled menu overflows ${size.width}x${size.height}`);
      await screenshot(`scaling-${size.width}-menu.png`);
      await page.keyboard.press('Escape');
    }
    await setViewportSize({ width: 1600, height: 1000 });
    await page.evaluate(async () => { await KfpsEditorPreferences.flush(); await flushPendingAutosave(); });
    await sourceIdentity('complete');
    report.workflowsPassed = true;
    report.passed = report.qualificationGaps.length === 0;
  } catch (error) {
    report.passed = false;
    report.error = String(error.stack || error);
    report.failureMetrics = await metrics().catch(() => null);
  } finally {
    writeReport();
    await session.send('Emulation.clearDeviceMetricsOverride');
    await session.detach();
  }
  return report;
}
