async (page, options = {}) => {
  const allowed = ['regression-workspace-tooltips.js', 'regression-editor-shortcuts.js',
    'regression-tool-workflows.js', 'regression-docking-edges.js',
    'regression-chrome-docking-persistence.js', 'regression-chrome-themes.js',
    'regression-host-editing-matrix.js', 'regression-panel-live-drag.js',
    'regression-render-cache-pixels.js', 'regression-mask-render.js', 'probe-chrome-reload.js'];
  const suite = options.chromeSuite;
  if (!options.browserHost || !allowed.includes(suite)) throw Error('Choose a reviewed Chrome functional suite');
  const tests = path.join(process.env.KFPS_TEST_APP_ROOT, 'KFPS.Editor/web/tests');
  const save = (name, data) => fs.writeFileSync(path.join(output, name), JSON.stringify(data, null, 2));
  const hash = value => crypto.createHash('sha256').update(value).digest('hex');
  const files = [...new Set([suite, 'dense-human-fixture.cjs', 'chrome-reload-adapter.cjs',
    ...(suite === 'regression-chrome-themes.js' ? ['regression-workspace-themes.js'] : []),
    ...(suite === 'regression-panel-live-drag.js' ? ['regression-host-editing-matrix.js'] : []),
    ...(suite === 'probe-chrome-reload.js' ? ['regression-chrome-docking-persistence.js', 'regression-docking-edges.js'] : []),
    ...(suite === 'regression-chrome-docking-persistence.js' ? ['regression-docking-edges.js'] : [])])];
  const sources = {};
  for (const file of files) {
    const source = fs.readFileSync(path.join(tests, file), 'utf8');
    fs.writeFileSync(path.join(output, 'test-inputs', file), source);
    sources[file] = hash(source);
  }
  save('functional-inputs.json', { suite, options, sources, timingInterpretation: 'Functional only; Qt may overlap' });
  const failures = [];
  const failed = request => {
    failures.push({ url: request.url(), resourceType: request.resourceType(), error: request.failure() });
    save('functional-network-failures.json', failures);
  };
  page.on('requestfailed', failed);
  page.setDefaultTimeout(20000);
  page.setDefaultNavigationTimeout(30000);
  try {
    const result = await eval(`(${fs.readFileSync(path.join(tests, suite), 'utf8')})`)(page, options);
    let closeSave;
    if (options.chromeSaveBeforeClose && result?.passed !== false) {
      const expected = await page.evaluate(() => JSON.stringify(snapshotShapes()));
      for (let i = 0; i < 3 && await page.locator('.workspaceMenu:popover-open').count(); i++) await page.keyboard.press('Escape');
      const name = 'Chrome close ' + path.basename(output);
      await page.locator('#workspaceFileMenu').click();
      await page.locator('#saveProjectAs').click();
      await page.locator('#textPromptInput').fill(name);
      await page.locator('#textPromptInput').press('Enter');
      await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty() && !editorCommands.busy);
      const info = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
      const file = path.join(info.profile, 'projects', name + '.fabric-project.json');
      const saved = JSON.parse(fs.readFileSync(file, 'utf8'));
      if (JSON.stringify(saved.shapes) !== expected || await page.evaluate(() => JSON.stringify(snapshotShapes())) !== expected) {
        throw Error('Save before normal close changed exact artwork');
      }
      closeSave = { file, exactShapes: true, viaActualUi: true };
      save('functional-close-save.json', closeSave);
    }
    const assets = JSON.parse(fs.readFileSync(path.join(output, 'asset-readback.json'), 'utf8'));
    const session = await page.context().newCDPSession(page);
    const parsed = new Map(), rows = [];
    session.on('Debugger.scriptParsed', entry => {
      const name = entry.url.split('/').pop().split('?')[0];
      if (assets.some(asset => asset.name === name)) parsed.set(name, entry.scriptId);
    });
    try {
      await session.send('Debugger.enable');
      for (const asset of assets) {
        if (!parsed.has(asset.name)) throw Error('Final page did not parse ' + asset.name);
        const source = await session.send('Debugger.getScriptSource', { scriptId: parsed.get(asset.name) });
        const actual = hash(source.scriptSource), disk = hash(fs.readFileSync(path.join(tests, '..', asset.name)));
        rows.push({ name: asset.name, actual, disk, initial: asset.expected,
          matched: actual === disk && actual === asset.expected });
        if (!rows.at(-1).matched) throw Error('Mixed/stale final source: ' + asset.name);
      }
    } finally {
      save('asset-readback-end.json', rows);
      await session.send('Debugger.disable');
      await session.detach();
    }
    for (const file of files) {
      if (hash(fs.readFileSync(path.join(tests, file))) !== sources[file]) throw Error('Test source changed during run: ' + file);
    }
    return { ...result, chromeSuite: suite, finalSourceReadback: true, closeSave };
  } finally {
    save('functional-network-failures.json', failures);
    page.removeListener('requestfailed', failed);
  }
}
