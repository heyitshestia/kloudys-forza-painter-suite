async page => {
  if (!await page.evaluate(() => favorites.has('Primitives:1'))) throw new Error('Shape favorite was lost across native process restart');
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({ hasText: 'Tool workflow persistence' }).click();
  await page.locator('#selectProjectEntry').click();
  if (await page.locator('#confirmationDialog').isVisible()) await page.locator('#confirmationDialogConfirm').click();
  await page.locator('#projectBrowserDialog').waitFor({ state: 'hidden' });
  const state = await page.evaluate(() => ({ name: currentProjectName, dirty: documentDirty,
    shapes: snapshotShapes(), favorite: favorites.has('Primitives:1') }));
  if (state.name !== 'Tool workflow persistence' || state.dirty || state.shapes.length !== 3
    || state.shapes[0].mask || !state.favorite) throw new Error('Tool workflow did not reopen after native process restart');
  return { nativeProcessRestart: true, favorite: true, projectReopen: true };
}
