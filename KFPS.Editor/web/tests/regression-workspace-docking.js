async (page, options = {}) => {
  const check = (ok, message) => { if (!ok) throw Error(message); };
  await page.setViewportSize({ width: 1600, height: 1000 });
  check(await page.locator('#workspacePanels').count() === 1, 'View > Panels is missing');
  const choose = async (id, action) => {
    const tab = page.locator(`.dockTab[data-panel="${id}"]`);
    await tab.click({ button: 'right' });
    await page.locator(`[data-dock-action="${action}"]`).click();
  };
  if (options.dockingRestart) {
    check(await page.locator('#propertiesPane').evaluate(node => !!node.closest('.workspaceLeftDock')), 'Left dock did not survive restart');
    check(await page.locator('#historyPane').evaluate(node => !!node.closest('.workspaceFloatingPanel')), 'Floating panel did not survive restart');
    await page.evaluate(() => KfpsDocking.reset());
    return { passed: true, restart: true };
  }
  await choose('propertiesPane', 'float');
  check(await page.locator('#propertiesPane').evaluate(node => !!node.closest('.workspaceFloatingPanel')), 'Properties did not detach');
  await choose('propertiesPane', 'left');
  check(await page.locator('#propertiesPane').evaluate(node => !!node.closest('.workspaceLeftDock')), 'Properties did not dock left');
  await choose('historyPane', 'float');
  const structure = await page.evaluate(() => ({
    tabs: [...document.querySelectorAll('.dockTab')].map(tab => tab.dataset.panel),
    duplicateIds: [...document.querySelectorAll('[id]')].map(node => node.id).filter((id, index, all) => all.indexOf(id) !== index),
    panels: readDockState().panels,
  }));
  check(!structure.duplicateIds.length, 'Docking duplicated bound controls');
  check(new Set(structure.tabs).size === structure.tabs.length, 'Docking duplicated tabs');
  await page.evaluate(() => KfpsEditorPreferences.flush());
  await page.mouse.move(500, 980);
  await page.screenshot({ path: path.join(output, 'docked-workspace.png') });
  return { passed: true, structure };
}
