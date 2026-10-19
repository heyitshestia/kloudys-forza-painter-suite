async (page) => {
  const checks = [];
  const check = (condition, message) => { if (!condition) throw Error(message); checks.push(message); };
  await page.setViewportSize({ width: 1600, height: 1000 });
  const tip = page.locator('#workspaceTooltip');
  const hover = async locator => {
    await locator.hover();
    await page.waitForFunction(node => (node.closest('[data-workspace-tooltip]')?.getAttribute('aria-describedby') || '').includes('workspaceTooltip')
      && !document.querySelector('#workspaceTooltip').hidden, await locator.elementHandle());
  };
  await hover(page.locator('#workspaceZoomIn'));
  check(await page.locator('#workspaceZoomIn').getAttribute('title') === null,
    'Native title must not compete with themed tooltip');
  check(await tip.isVisible() && await tip.innerText() === 'Zoom in', 'Themed tooltip is readable');
  check(await page.locator('#workspaceTooltip:popover-open').count() === 1, 'Tooltip uses the browser top layer');
  check(await page.locator('body [title]').count() === 0, 'Initial native titles transferred');
  for (const id of ['quickColorSwatch', 'colorSwatchButton', 'colorPanelSwatch']) {
    check(Boolean(await page.locator(`#${id}`).getAttribute('aria-label')), `${id} retains an accessible name`);
  }
  await page.keyboard.press('Escape');
  check(!await tip.isVisible(), 'Escape dismisses tooltip');
  await page.locator('#workspaceZoomOut').focus();
  check(await tip.isVisible() && await tip.innerText() === 'Zoom out', 'Keyboard focus shows tooltip');
  await page.locator('#workspaceZoomOut').press('Tab');
  check(!(await page.locator('#workspaceZoomOut').getAttribute('aria-describedby') || '').includes('workspaceTooltip'),
    'Focus departure removes tooltip description');

  await page.evaluate(() => {
    const fixture = document.createElement('div'); fixture.id = 'tooltipFixture';
    fixture.style.cssText = 'position:fixed;left:400px;top:350px;z-index:100000;padding:10px;background:var(--panel)';
    fixture.innerHTML = '<button id="tooltipProbe" title="Initial hint" aria-describedby="existingHelp"><span>Probe</span></button><span id="existingHelp">Existing description</span>';
    document.body.append(fixture);
  });
  const probe = page.locator('#tooltipProbe');
  await hover(probe);
  check(await probe.getAttribute('title') === null && await tip.innerText() === 'Initial hint', 'Dynamic controls use themed tooltip');
  check(await probe.getAttribute('aria-describedby') === 'existingHelp workspaceTooltip', 'Existing accessible description preserved');
  await page.evaluate(() => { const p = document.querySelector('#tooltipProbe'); p.title = 'Changed hint'; p.dataset.workspaceShortcut = 'Ctrl+9'; });
  await page.waitForFunction(() => document.querySelector('#workspaceTooltip').textContent === 'Changed hint (Ctrl+9)');
  check(await probe.getAttribute('title') === null, 'Dynamic title updates suppress native tooltip');
  await hover(probe.locator('span'));
  check(await tip.isVisible(), 'Moving within a control keeps tooltip');
  await page.evaluate(() => { document.querySelector('#tooltipProbe span').title = 'Nested hint'; });
  await page.mouse.move(800, 500); await hover(probe.locator('span'));
  check(await tip.innerText() === 'Nested hint', 'Nested control uses its own tooltip');
  await page.evaluate(() => document.querySelector('#tooltipProbe span').removeAttribute('data-workspace-tooltip'));
  await page.mouse.move(800, 500); await hover(probe);
  await page.evaluate(() => document.querySelector('#tooltipProbe').setAttribute('aria-describedby', 'existingHelp workspaceTooltip laterHelp'));
  await page.mouse.move(800, 500);
  await page.evaluate(() => { document.querySelector('#tooltipProbe').title = 'Updated while leaving'; });
  await page.waitForFunction(() => document.querySelector('#workspaceTooltip').hidden);
  check(!await tip.isVisible() && await probe.getAttribute('aria-describedby') === 'existingHelp laterHelp',
    'Tooltip exit preserves descriptions added while open');
  check(!await tip.isVisible(), 'Dynamic refresh cannot cancel pending dismissal');
  await hover(probe);
  await page.evaluate(() => { document.querySelector('#tooltipProbe').title = ''; });
  await page.waitForFunction(() => document.querySelector('#workspaceTooltip').hidden);
  check(!await tip.isVisible(), 'Empty title clears an active tooltip');
  await page.evaluate(() => { const p = document.querySelector('#tooltipProbe'); p.title = 'Disabled hint'; p.disabled = true; });
  await page.mouse.move(800, 500); await hover(probe);
  check(await tip.innerText() === 'Disabled hint (Ctrl+9)', 'Disabled controls retain hover help');
  await page.evaluate(() => document.dispatchEvent(new Event('scroll', { bubbles: false })));
  check(!await tip.isVisible(), 'Scroll dismisses tooltip');
  await page.mouse.move(800, 500); await hover(probe);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.waitForFunction(() => document.querySelector('#workspaceTooltip').hidden);
  check(!await tip.isVisible(), 'Resize dismisses stale tooltip');
  await page.mouse.move(800, 500); await hover(probe);
  await page.evaluate(() => document.querySelector('#tooltipFixture').remove());
  await page.waitForFunction(() => document.querySelector('#workspaceTooltip').hidden);
  check(!await tip.isVisible(), 'Removed owner cannot leave tooltip behind');

  await page.locator('#workspaceViewMenu').click();
  await hover(page.locator('#workspaceReset'));
  check(await tip.isVisible(), 'Menu item tooltip appears');
  await page.locator('#workspaceReset').click();
  check(!await tip.isVisible(), 'Click does not immediately reopen a tooltip');
  await page.locator('#workspaceViewMenu').click();
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Escape');
  check(!await tip.isVisible(), 'Escape focus restoration does not reopen tooltip');
  await hover(page.locator('#workspaceZoomIn'));
  await page.mouse.down();
  await page.locator('#workspaceZoomOut').hover();
  check(!await tip.isVisible(), 'Dragging across controls does not open tooltips');
  await page.mouse.up();

  await page.evaluate(() => {
    const dialog = document.createElement('dialog'); dialog.id = 'tooltipDialog';
    dialog.innerHTML = '<button title="Modal help">Modal probe</button>';
    document.body.append(dialog); dialog.showModal();
  });
  await hover(page.locator('#tooltipDialog button'));
  check(await tip.isVisible() && await tip.innerText() === 'Modal help', 'Modal tooltip appears above dialog');
  const modalBox = await tip.boundingBox();
  await page.mouse.move(modalBox.x + modalBox.width / 2, modalBox.y + modalBox.height / 2, { steps: 3 });
  check(await tip.isVisible() && await tip.evaluate(el => {
    const box = el.getBoundingClientRect();
    return el.contains(document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2));
  }), 'Modal tooltip is hoverable, not inert behind the dialog');
  await page.screenshot({ path: path.join(output, 'tooltip-modal.png') });
  await page.evaluate(() => { const d = document.querySelector('#tooltipDialog'); d.close(); d.remove(); });
  await page.waitForFunction(() => document.querySelector('#workspaceTooltip').hidden);
  check(!await tip.isVisible(), 'Dialog close dismisses tooltip');
  await hover(page.locator('#workspaceZoomIn'));
  const hoverBox = await tip.boundingBox();
  await page.mouse.move(hoverBox.x + hoverBox.width / 2, hoverBox.y + hoverBox.height / 2, { steps: 3 });
  check(await tip.isVisible(), 'Tooltip remains available when moving onto its text');
  await page.mouse.move(800, 500);
  await page.waitForFunction(() => document.querySelector('#workspaceTooltip').hidden);
  check(!await tip.isVisible(), 'Leaving tooltip text dismisses it');
  await page.setViewportSize({ width: 760, height: 640 });
  await page.evaluate(() => {
    const probe = document.createElement('button'); probe.id = 'tooltipEdge';
    probe.title = 'A'.repeat(400); probe.textContent = 'Edge';
    probe.style.cssText = 'position:fixed;right:0;bottom:0;z-index:100000'; document.body.append(probe);
  });
  await hover(page.locator('#tooltipEdge'));
  const box = await tip.boundingBox();
  check(box.x >= 0 && box.y >= 0 && box.x + box.width <= 760 && box.y + box.height <= 640,
    'Long tooltip stays within small viewport');
  check(await tip.evaluate(el => el.scrollWidth <= el.clientWidth), 'Unbroken text wraps instead of overflowing');
  await page.evaluate(() => document.querySelector('#tooltipEdge').remove());
  await page.setViewportSize({ width: 1600, height: 1000 });
  for (const theme of ['pastel', 'dark', 'blackout', 'whiteout']) {
    await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
    await page.mouse.move(800, 500); await hover(page.locator('#workspaceZoomIn'));
    const colors = await tip.evaluate(el => {
      const control = document.createElement('div'); control.style.cssText = 'background:var(--panel);color:var(--text)'; document.body.append(control);
      const expected = getComputedStyle(control), actual = getComputedStyle(el);
      const result = { same: expected.backgroundColor === actual.backgroundColor && expected.color === actual.color };
      control.remove(); return result;
    });
    check(colors.same, `${theme} tooltip uses theme tokens`);
    await page.screenshot({ path: path.join(output, `tooltip-${theme}.png`) });
  }
  await page.keyboard.press('Escape');
  check(await page.locator('body [title]').count() === 0, 'No native tooltip titles reintroduced');
  return { passed: true, checks };
}
