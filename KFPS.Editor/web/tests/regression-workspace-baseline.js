async (page) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.evaluate(async () => {
    await loadPayload({ shapes: Array.from({ length: 240 }, (_, i) => ({
      type: [1048677, 1048678, 1048679][i % 3],
      color: [[232, 90, 134, 255], [61, 174, 181, 255], [242, 190, 75, 255]][i % 3],
      data: [(i % 20) * 70 - 660, Math.floor(i / 20) * 70 - 380, .25, .25, i % 5 * 15, 0, 0],
      editor_id: `workspace-${i}`, editor_name: `Shape ${i + 1}`,
    })) });
    selectObjects([vinylObjects()[10]], 'test');
  });
  if (await page.locator('#workspaceViewMenu').count()) await page.locator('#workspaceViewMenu').click();
  await page.locator('#fitView').click();
  const geometry = await page.evaluate(() => Object.fromEntries(
    ['.canvasStage', '.rightDock', '.appBar', '.contextBar', '#layersViewport'].map(selector => {
      const r = document.querySelector(selector).getBoundingClientRect();
      return [selector, { x: r.x, y: r.y, width: r.width, height: r.height }];
    })));
  await page.mouse.move(500, 980);
  await page.screenshot({ path: path.join(output, 'workspace-1600.png') });
  if (await page.locator('#workspaceFileMenu').count()) await page.locator('#workspaceFileMenu').click();
  await page.locator('#saveProjectAs').click();
  await page.locator('#textPromptInput').fill('Workspace baseline');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  return { geometry, saved: true, layers: await page.evaluate(() => vinylObjects().length),
    controls: await page.evaluate(() => ['undoBtn','saveProject'].map(id => document.getElementById(id).outerHTML)),
    overflow: await page.evaluate(() => [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().bottom > innerHeight + 1 && getComputedStyle(el).position === 'absolute').map(el => [el.id, el.className]).slice(0, 20)) };
}
