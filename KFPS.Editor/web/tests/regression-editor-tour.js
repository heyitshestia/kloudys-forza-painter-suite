async (page) => {
  const checks = [];
  const check = (condition, message) => {
    if (!condition) throw Error(message);
    checks.push(message);
  };
  const settle = async () => {
    await page.evaluate(() => new Promise(resolve =>
      requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.locator('#editorTourCard').evaluate(async card => {
      await Promise.all(card.getAnimations().map(animation => animation.finished.catch(() => {})));
    });
  };
  const inspectCard = () => page.locator('#editorTourCard').evaluate(card => {
    const box = card.getBoundingClientRect();
    const points = [];
    for (const x of [0.06, 0.5, 0.94]) {
      for (const y of [0.08, 0.5, 0.92]) {
        points.push([box.left + box.width * x, box.top + box.height * y]);
      }
    }
    points.push([box.left + 3, box.top + box.height / 2], [box.right - 3, box.top + box.height / 2]);
    for (const button of card.querySelectorAll('button:not(:disabled)')) {
      const rect = button.getBoundingClientRect();
      points.push([rect.left + rect.width / 2, rect.top + rect.height / 2]);
    }
    return {
      inside: box.left >= 0 && box.top >= 0 && box.right <= innerWidth && box.bottom <= innerHeight,
      readable: box.width > 200 && box.height > 100 && card.scrollWidth <= card.clientWidth,
      covered: points.filter(([x, y]) => !card.contains(document.elementFromPoint(x, y))),
    };
  });
  const verifyCard = async label => {
    await settle();
    const result = await inspectCard();
    check(result.inside && result.readable, `${label}: card fits the viewport`);
    check(result.covered.length === 0,
      `${label}: text and buttons are above the highlighted target (${JSON.stringify(result.covered)})`);
  };
  const verifyClosed = async label => {
    const state = await page.evaluate(() => ({
      active: Boolean(editorTourState?.active),
      hidden: document.querySelector('#editorTourLayer').hidden,
      targets: document.querySelectorAll('.editorTourTarget').length,
      body: document.body.classList.contains('editorTourActive'),
    }));
    check(!state.active && state.hidden && !state.targets && !state.body, `${label}: tour layers are removed`);
  };

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.evaluate(() => {
    editorTheme.applyEditorTheme('whiteout', { persist: false });
    startEditorTour();
    showTourStep(2);
  });
  await settle();
  await page.screenshot({ path: path.join(output, 'tour-canvas-whiteout.png') });
  await verifyCard('Reported canvas overlap');
  await page.locator('#editorTourBack').click();
  check(await page.evaluate(() => editorTourState.index) === 1, 'Back changes the tour step');
  await page.locator('#editorTourSkip').click();
  await verifyClosed('Skip');

  for (const [theme, width, height] of [
    ['whiteout', 1920, 1080],
    ['dark', 1760, 1040],
    ['blackout', 1280, 800],
    ['pastel', 960, 640],
  ]) {
    await page.setViewportSize({ width, height });
    await page.evaluate(theme => {
      editorTheme.applyEditorTheme(theme, { persist: false });
      startEditorTour();
    }, theme);
    const total = await page.evaluate(() => EDITOR_TOUR_STEPS.length);
    check(await page.locator('#editorTourBack').isDisabled(), `${theme}: first step disables Back`);
    for (let index = 0; index < total; index++) {
      check(await page.evaluate(() => editorTourState.index) === index, `${theme}: step ${index + 1} reached`);
      await verifyCard(`${theme} ${width}x${height} step ${index + 1}`);
      if (index === 2) await page.screenshot({ path: path.join(output, `tour-canvas-${theme}-${width}.png`) });
      await page.locator('#editorTourNext').click();
    }
    await verifyClosed(`${theme} Finish`);
  }

  await page.evaluate(() => { startEditorTour(); showTourStep(2); });
  for (const [width, height] of [[1920, 1080], [1280, 720], [960, 640]]) {
    await page.setViewportSize({ width, height });
    await verifyCard(`Active-tour resize ${width}x${height}`);
  }
  await page.keyboard.press('Escape');
  await verifyClosed('Escape');
  await page.evaluate(() => startEditorTour());
  await verifyCard('Restart after Escape');
  await page.locator('#editorTourSkip').click();
  await verifyClosed('Repeated Skip');
  return { passed: true, checks };
}
