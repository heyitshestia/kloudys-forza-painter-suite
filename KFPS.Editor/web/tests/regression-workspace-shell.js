async (page) => {
  const check = (condition, message) => { if (!condition) throw Error(message); };
  await page.setViewportSize({ width: 1600, height: 1000 });
  check(await page.locator('#workspaceReset').count() === 1, 'Workspace reset is missing');
  const geometry = await page.evaluate(() => ({
    canvas: document.querySelector('.canvasStage').getBoundingClientRect().width,
    rows: document.querySelector('#layersViewport').clientHeight,
    menus: document.querySelectorAll('.workspaceMenuTrigger').length,
    icons: document.querySelectorAll('.toolRail svg').length,
  }));
  check(geometry.canvas >= 1100, 'Canvas remains too narrow');
  check(geometry.rows >= 250, 'Layer list remains cramped');
  check(geometry.menus >= 4 && geometry.icons >= 8, 'Commands or tools not discoverable');
  await page.locator('#workspaceViewMenu').click();
  await page.locator('#workspaceReset').click();
  check(await page.locator('.workspaceMenu:popover-open').count() === 0, 'Command menu stayed open');
  await page.locator('#workspaceFileMenu').click();
  await page.keyboard.press('ArrowUp');
  check(await page.evaluate(() => document.activeElement === document.querySelector('#workspaceFileCommands button:last-child')),
    'Arrow Up did not enter the menu at its last command');
  await page.keyboard.press('Escape');
  await page.locator('#workspaceFileMenu').click();
  await page.keyboard.press('ArrowDown');
  check(await page.evaluate(() => document.activeElement === document.querySelector('#workspaceFileCommands button')),
    'Arrow Down did not enter the menu at its first command');
  await page.keyboard.press('Escape');
  check(await page.locator('#workspaceFileMenu').evaluate(el => el === document.activeElement), 'Menu focus not restored');
  check(await page.locator('#hudHover').isVisible(), 'Hovered-layer feedback is hidden');
  const splitter = page.locator('#workspaceDockWidth');
  await splitter.focus();
  await page.keyboard.press('ArrowLeft');
  check(await page.evaluate(() => readDockState().width === 400), 'Keyboard dock resize failed');
  await page.keyboard.press('Home');
  check(await page.evaluate(() => readDockState().width === 384), 'Dock width reset failed');
  const layouts = [];
  for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) {
    await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
    for (const width of [900, 1280, 1600, 1920]) {
      await page.setViewportSize({ width, height: width === 900 ? 700 : 1000 });
      const result = await page.evaluate(() => {
        const canvas = document.querySelector('.canvasStage').getBoundingClientRect();
        const dock = document.querySelector('.rightDock').getBoundingClientRect();
        return { canvas: canvas.width, dock: dock.width, overflow: document.documentElement.scrollWidth > innerWidth,
          stageHeight: canvas.height, documentHeight: document.documentElement.scrollHeight };
      });
      check(!result.overflow && result.canvas >= 300 && result.stageHeight >= 400 && result.documentHeight <= (width === 900 ? 700 : 1000), `Bad layout ${theme}/${width}: ${JSON.stringify(result)}`);
      layouts.push({ theme, width, ...result });
    }
    await page.screenshot({ path: path.join(output, `workspace-${theme}.png`) });
  }
  return { geometry, layouts, menus: true, keyboardResize: true };
}
