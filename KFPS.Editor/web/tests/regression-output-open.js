async (page) => {
  const assert = require('node:assert/strict');
  const {spawnSync} = require('node:child_process');
  const info = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
  const title = 'Outputs # & \u65e5\ud55c';
  const filename = title + '.JSON';
  const id = '@exports/' + filename;
  const group = (id, name) => ({id, name});
  const shapes = Array.from({length: 12}, (_, i) => ({
    type: 1048677, data: [(i % 4) * 80, Math.floor(i / 4) * 80, .4, .4, 0, 0, 0],
    color: [40 + i * 15, 130, 210, 255], editor_id: 'output-shape-' + i,
    ...(i < 10 ? {editor_group_path: [group('root', 'Root'), group(i < 5 ? 'blue' : 'pink', i < 5 ? 'Blue' : 'Pink'),
      ...([1, 2, 3, 6, 7, 8].includes(i) ? [group(i < 5 ? 'bars' : 'dots', i < 5 ? 'Bars' : 'Dots')] : [])]} : {}),
  }));
  fs.mkdirSync(info.exportRoot, {recursive: true});
  const file = path.join(info.exportRoot, filename);
  const source = JSON.stringify({shapes});
  fs.writeFileSync(file, source);
  fs.writeFileSync(path.join(info.exportRoot, 'bad.json'), '{broken');
  fs.writeFileSync(path.join(info.exportRoot, 'invalid.json'), '{"shapes":[]}');
  const send = (jsonId) => {
    const code = 'import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); '
      + 'from kfps_editor.ipc import forward_request,instance_name; '
      + 'assert forward_request(instance_name(Path(sys.argv[2]),Path(sys.argv[3])), '
      + '{"json":sys.argv[4],"mode":"activate","background":True})';
    const result = spawnSync(path.join(info.appRoot, 'python', 'python.exe'),
      ['-B', '-c', code, path.join(info.appRoot, 'KFPS.Editor', 'src'), info.appRoot, info.profile, jsonId],
      {windowsHide: true, encoding: 'utf8', timeout: 15000});
    assert.equal(result.status, 0, result.stderr || String(result.error));
  };
  let saves = 0;
  const save = async () => {
    await page.evaluate(() => { void saveProject({saveAs: true}); });
    await page.locator('#textPromptInput').fill('Outputs menu qualification ' + (++saves));
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty());
  };
  const snapshot = () => page.evaluate(() => JSON.stringify(editableProjectPayload('check').shapes));
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  send(id);
  await page.waitForFunction(() => vinylObjects().length === 12);
  assert.deepEqual(await page.evaluate(() => editableProjectPayload('check').shapes.map(s => (s.editor_group_path || []).length)),
    shapes.map(s => (s.editor_group_path || []).length));
  await page.screenshot({path: path.join(output, 'output-open.png')});
  await page.evaluate(async () => { await addShape('Primitives', 2); });
  const beforeCancel = await snapshot();
  send(id);
  await page.locator('#confirmationDialog[open]').waitFor();
  await page.locator('#confirmationDialogCancel').click();
  await page.waitForFunction(() => !document.querySelector('dialog[open]'));
  assert.equal(await snapshot(), beforeCancel);
  send(id);
  await page.locator('#confirmationDialog[open]').waitFor();
  await page.locator('#confirmationDialogConfirm').click();
  await page.waitForFunction(() => vinylObjects().length === 12);
  await save();
  const good = await snapshot();
  for (const bad of ['@exports/missing.json', '@exports/bad.json', '@exports/invalid.json', 'runtime/private.json']) {
    const error = await page.evaluate(async id => {
      try { await openOutputJson(id); return ''; } catch (e) { return String(e); }
    }, bad);
    assert.ok(error, bad);
    assert.equal(await snapshot(), good, 'A failed load replaced the current canvas: ' + bad);
  }
  // Exercise the same encoded query that the native and Chrome cold launch uses.
  const url = new URL(page.url());
  url.searchParams.set('json', id);
  await page.evaluate(() => { window.__KfpsBrowserCloseAllowed = true; });
  await page.goto(url.href);
  await page.waitForFunction(() => window.KfpsDesktop?.ready && vinylObjects().length === 12);
  assert.equal(await page.evaluate(() => startupJsonId()), id);
  assert.equal(await page.locator('#jsonBrowserDialog[open]').count(), 0);
  assert.equal(fs.readFileSync(file, 'utf8'), source, 'Opening overwrote the source JSON');
  await save();
  return {passed: true, layers: 12, nestedGroups: 5, looseShapes: 2, ipcOpen: true,
    cancelKeptEdits: true, replaceConfirmed: true, rejectedLoadsPreservedCanvas: 4,
    startupQuery: true, sourceUnchanged: true};
}
