async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  page.setDefaultTimeout(30000);
  const initial = await h.setup(page, output, options);
  const original = await h.snapshot(page), reference = await h.referenceState(page);
  const trace = await h.monitor(page, output), checks = [];
  const tool = mode => page.locator(`[data-tool-mode="${mode}"]`).click();
  const range = async (id, value) => {
    const input = page.locator(id), minimum = Number(await input.getAttribute("min") || 0);
    await input.focus(); await input.press("Home");
    for (let index = minimum; index < value; index++) await input.press("ArrowRight");
  };
  try {
    await tool("overlay");
    for (const order of ["below", "above"]) {
      await page.locator("#overlayLayerMode").selectOption(order);
      for (const opacity of [0, 1, 45, 99, 100]) await trace.run(`${order}/reference-opacity-${opacity}`, async () => {
        const before = (await h.referenceState(page)).transform;
        await range("#overlayOpacity", opacity);
        const after = (await h.referenceState(page)).transform;
        h.check(Math.abs(after.opacity - opacity / 100) < 1e-9, "Reference opacity did not apply");
        delete before.opacity; delete after.opacity;
        h.check(JSON.stringify(after) === JSON.stringify(before), "Opacity changed reference placement or size");
        h.check(await h.snapshot(page) === original, "Reference opacity edited vinyl shapes");
      });
      await range("#overlayOpacity", 45);
      for (const size of [10, 100, 400]) await trace.run(`${order}/reference-size-${size}`, async () => {
        await h.type(page, "#overlayScalePercent", size);
        await page.locator("#overlayScalePercent").press("Enter");
        h.check((await h.referenceState(page)).controls.scale_percent === size, "Reference size control did not apply");
      });
      for (let round = 0; round < 3; round++) {
        await page.locator("#toggleOverlay").click();
        h.check(!await page.evaluate(() => editorReference.image.visible), "Reference did not hide");
        await page.locator("#toggleOverlay").click();
        h.check(await page.evaluate(() => editorReference.image.visible), "Reference did not show");
      }
      await tool("source");
      const box = await page.locator(".upper-canvas").boundingBox();
      const start = { x: box.x + box.width * .5, y: box.y + box.height * .5 };
      for (const speed of Object.keys(h.speeds)) await trace.run(`${order}/reference-move-${speed}`, async () => {
        const before = await h.referenceState(page);
        await h.motion(page, start, { x: start.x + 17, y: start.y + 12 }, speed);
        const after = await h.referenceState(page);
        h.check(Math.hypot(after.transform.left - before.transform.left, after.transform.top - before.transform.top) > .01, "Move Reference did not move it");
        h.check(await h.snapshot(page) === original, "Moving the reference changed artwork");
      });
      await tool("overlay");
    }
    checks.push("Both orders, five opacity levels, three sizes, six hide/show cycles, all four reference drag speeds; shapes unchanged");
    await h.saveAs(page, "Handmade reference checkpoint");
    const savedReference = await h.referenceState(page);
    await page.locator("#newCanvas").click();
    await page.waitForFunction(() => vinylObjects().length === 0);
    await h.openStored(page, "Handmade reference checkpoint", initial.layers);
    await page.waitForFunction(() => !!editorReference.image);
    h.check(JSON.stringify(await h.referenceState(page)) === JSON.stringify(savedReference), "Reference controls/transform changed on reopen");
    h.check(await h.snapshot(page) === original, "Reference project reopen changed artwork");
    await tool("overlay");
    await page.locator("#removeOverlay").click();
    await page.waitForFunction(() => !editorReference.image);
    h.check(await h.snapshot(page) === original, "Removing reference changed artwork");
    await h.fileInput(page, "#overlayInput", options.reference);
    await page.waitForFunction(() => !!editorReference.image);
    h.check(await page.evaluate(() => editorReference.image.width) === initial.reference[0], "Reference replacement dimensions wrong");
    await h.saveAs(page, "Handmade replaced reference");
    await page.evaluate(async () => { await flushPendingAutosave(); });
    await page.screenshot({ path: path.join(output, "handmade-reference-final.png") });
    return { initial, reference, rows: trace.rows, checks, exactArtwork: true, exactReferenceReopen: true,
      replacement: true, removal: true };
  } finally { await trace.close(); }
}
