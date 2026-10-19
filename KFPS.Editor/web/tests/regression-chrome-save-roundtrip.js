async (page) => {
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const name = 'Chrome qualification ' + path.basename(output);
  const state = await page.evaluate(() => ({
    shapes: JSON.stringify(snapshotShapes()),
    portable: JSON.stringify(vinylObjects().map(object => objectToShape(object, { includeEditorMeta: false }))),
    reference: JSON.stringify(editorReference.sourceOverlayProjectState()),
    count: vinylObjects().length,
  }));
  for (let i = 0; i < 3 && await page.locator('.workspaceMenu:popover-open').count(); i++) await page.keyboard.press('Escape');
  await page.locator('#workspaceFileMenu').click();
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill(name);
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !isDocumentDirty());
  const processInfo = JSON.parse(fs.readFileSync(path.join(output, 'process.json'), 'utf8'));
  const projectPath = path.join(processInfo.profile, 'projects', name + '.fabric-project.json');
  const saved = JSON.parse(fs.readFileSync(projectPath, 'utf8'));
  check(JSON.stringify(saved.shapes) === state.shapes, 'Disk project changed exact shapes');
  await page.locator('#exportJson').click();
  await page.waitForFunction(() => !exportSaveInProgress && !editorCommands.busy);
  const exportedPath = fs.readdirSync(processInfo.exportRoot, { recursive: true }).find(file => file.endsWith('.json'));
  check(exportedPath, 'No on-disk portable export');
  const exported = JSON.parse(fs.readFileSync(path.join(processInfo.exportRoot, exportedPath), 'utf8'));
  check(JSON.stringify(exported.shapes) === state.portable, 'Portable export changed artwork or contains helpers');
  await page.locator('#workspaceFileMenu').click();
  await page.locator('#newCanvas').click();
  await page.waitForFunction(() => !editorCommands.busy && vinylObjects().length === 0);
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({ has: page.getByText(name, { exact: true }) }).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(count => !editorCommands.busy && !recoveryRestoreDepth && vinylObjects().length === count, state.count);
  check(await page.evaluate(() => JSON.stringify(snapshotShapes())) === state.shapes, 'Project-picker reopen changed artwork');
  check(await page.evaluate(() => JSON.stringify(editorReference.sourceOverlayProjectState())) === state.reference,
    'Project-picker reopen changed reference');
  await page.screenshot({ path: path.join(output, 'saved-reopened.png') });
  const result = { passed: true, layers: state.count, exactProject: true, exactPortableExport: true,
    exactReopen: true, referenceRoundtrip: true, projectPath, exportedPath };
  fs.writeFileSync(path.join(output, 'chrome-save-roundtrip.json'), JSON.stringify(result, null, 2));
  return result;
}
